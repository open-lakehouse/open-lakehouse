---
name: delta-sharing
description: Delta Sharing on this stack — the OpenSharing reference server + the url-rewriter re-signing proxy, why the proxy exists (the T-4.8 upstream signer bug), how re-signing reconciles with SeaweedFS presigned host-rewrite, the `./lakehouse share` CLI, the shared-table seed, the client profile + self-signed-cert caveat, and local-vs-tunnel delivery. Load when starting/debugging Delta Sharing or reasoning about presigned-URL signing.
---

# Delta Sharing

Opt-in demo service (deliberately **not** part of `start all`). Serves the tables
declared in `docker/delta-sharing/server.yaml` over the Delta Sharing protocol on
**HTTPS 8443** (self-signed). Brought up with `./lakehouse share start`.

## Topology

```
client ──HTTPS 8443──► url-rewriter-proxy.py ──HTTPS 8444──► OpenSharing server ──S3──► SeaweedFS:8333
         (re-signs the presigned URLs in the server's JSON responses)
```

One container (`delta-sharing`): `entrypoint.sh` (bash) is **PID 1**. It starts the
OpenSharing JVM server on internal **8444** and the proxy on external **8443** as
**background jobs**, installs a `trap` on SIGTERM/SIGINT (`cleanup()` kills both),
and `wait`s on the proxy. It deliberately does **not** `exec` the proxy — `exec`
would replace the shell and discard the trap, so on `docker stop` the Java server
would be force-killed; with the `wait`+trap pattern, both stop cleanly. Both use a
self-signed cert generated at startup. The image is `eclipse-temurin:11` + the
Delta Sharing 1.3.10 server JARs (fetched by coursier).

## Why the proxy exists — the T-4.8 upstream signer bug

The OpenSharing server generates the presigned S3 URLs clients use to fetch data.
**It ignores `fs.s3a.endpoint` and always signs them for `s3.amazonaws.com`** —
`CloudFileSigner.scala` constructs `S3ClientCreationParameters()` empty, so
Hadoop's `DefaultS3ClientFactory` defaults the endpoint to AWS. This breaks every
S3-compatible store (SeaweedFS, MinIO, Ceph…). Upstream:
`delta-io/delta-sharing#753`; the 7-line fix PR `#965` is stalled awaiting review.

**Workaround = the proxy re-signs.** `url-rewriter-proxy.py` intercepts the
server's JSON responses, extracts bucket+key from each presigned URL, and computes
a **brand-new SigV4 signature** for the real endpoint (`S3_PUBLIC_ENDPOINT`). It
does *not* just swap the host — SigV4 covers `host`, so a naive swap would
invalidate the signature.

## How re-signing reconciles with SeaweedFS

The proxy re-signs for `S3_PUBLIC_ENDPOINT` (the host the *client* will reach):

- **Local (default):** `S3_PUBLIC_ENDPOINT=localhost:8333`, scheme `http`. The
  signed host == the delivered host, so it's plain SigV4 — verifies directly, no
  tunnel or forwarding headers. This is what `./lakehouse share` uses out of the box.
- **Public tunnel:** set `S3_PUBLIC_ENDPOINT` to the tunnel host (+ `S3_PUBLIC_SCHEME=https`).
  The URL is signed for the public host but lands on local SeaweedFS; SeaweedFS
  verifies it via `X-Forwarded-Host` (mode B) or a `Host:` override (mode C). See
  [[seaweedfs-ops]] §2.2 — this is SeaweedFS's edge over MinIO, locked in by
  `scripts/connectivity/test-presigned-host-rewrite.py` (S-07/S-08).

## CLI

```bash
./lakehouse share seed      # write the shared tables — needs storage (8333) AND Spark Connect
./lakehouse share start     # build + up, wait for 8443, write ./lakehouse.share
./lakehouse share status    # container + HTTP probe
./lakehouse share stop
./lakehouse share profile   # (re)write the client profile
```

`share seed` gates on both SeaweedFS (8333, it boto3-clears the S3 prefix first)
and Spark Connect, so a missing service gives a friendly error, not a raw traceback.

`share start` mints a bearer token host-side if `DELTA_SHARING_TOKEN` is unset and
passes it to the container **via Compose** (so it's a real container env var). Thus
`share profile` in a fresh shell recovers it with
`docker exec delta-sharing printenv DELTA_SHARING_TOKEN` (`share_container_token`) —
this works precisely because the token is a Compose `environment:` value, not an
entrypoint-only `export`. `reset` restarts sharing without re-minting or rebuilding
(`share_restore`): it reuses the token from the env or the profile, and skips the
restart if neither is available rather than let the entrypoint mint an unknowable one.

## What's shared + the seed

`docker/delta-sharing/server.yaml` shares one share (`lakehouse_share`), schema
`retail`, two tables at **fixed, path-based** locations:

- `s3a://lakehouse/warehouse/sharing/sales_by_region/`
- `s3a://lakehouse/warehouse/sharing/daily_revenue/`

`scripts/sharing/seed_shared_tables.py` writes them via Spark Connect (boto3-clears
the prefix first for clean re-runs). **Path-based, not catalog-managed:** Delta
Sharing reads a table by its physical `_delta_log`, so it needs a stable location —
not an opaque UC-managed `__unitystorage/<uuid>` path. This also makes the demo
self-contained (no other demo need have run). `server.yaml`'s own comment warns:
only list tables that have valid Delta logs, or the server 400/500s.

## Client profile + self-signed caveat

`./lakehouse share` writes `lakehouse.share` (gitignored — it holds the bearer
token):

```json
{ "shareCredentialsVersion": 1, "endpoint": "https://localhost:8443/delta-sharing", "bearerToken": "…" }
```

The server uses a **self-signed cert**, so a Delta Sharing client must trust it (or
skip TLS verification). For a quick check without a client, hit the REST API with
`curl -k -H "Authorization: Bearer <token>"`.

## Gotchas

- **Delta-format consumers need a checkpoint.** Databricks (and other real
  clients) send `delta-sharing-capabilities: responseformat=delta`; the server's
  Delta Kernel reader then treats a missing `_delta_log/_last_checkpoint` as fatal
  (`DeltaSharedTableKernel.query` → `FileNotFoundException`). A fresh single-commit
  Delta table has no checkpoint. The seed forces one (`delta.checkpointInterval=1`
  + a second commit). Any new shared table must do the same. The parquet-format
  path (`responseformat=parquet`, the default for a bare `curl`) tolerates the
  absence — so a `curl` test passing does NOT prove Databricks can read it.
- **A remote consumer (e.g. Databricks)** needs the sharing API and SeaweedFS
  reachable at a public HTTPS endpoint (any ingress — reverse proxy, tunnel, LB),
  plus `S3_PUBLIC_ENDPOINT`=that host + `S3_PUBLIC_SCHEME=https`. Verified: provider
  → catalog → `SELECT` returns rows (the client fetches parquet from SeaweedFS via
  that endpoint, modes B/C). How you expose it is out of scope for this repo.
- **No `depends_on: seaweedfs`** — storage is a separate compose file, so a
  cross-file depends_on would break `docker compose -f docker-compose-sharing.yml
  up`. The CLI sequences ordering (mirrors mlflow/airflow).
- **Build needs a package proxy here** — coursier (Maven) + `pip install requests`
  can't reach public indexes in this sandbox. Pass `MAVEN_REPO_URL` / `PIP_INDEX_URL`
  as build-args at invocation; committed defaults stay public ([[databricks-build-proxies]]).
- **Bucket is `lakehouse`** (not the CP `lakehouse-data`); endpoint `seaweedfs:8333`
  in-network, `localhost:8333` from the host.
- `./lakehouse logs` doesn't cover delta-sharing; use `docker logs delta-sharing`
  (server log is inside the container at `/var/log/delta-sharing/server.log`).
