---
name: seaweedfs-ops
description: SeaweedFS 3.80 as the S3 object store in this stack — auth/identities config, port map, the file-vs-directory limit, presigned host-rewrite semantics (why it beats MinIO for Delta Sharing), the conditional-PUT / SeaweedFS-4.x tradeoff, and the Colima bind-mount gotcha. Load when configuring SeaweedFS, debugging S3 auth/presigned URLs, or reasoning about S3 compatibility.
---

# SeaweedFS operations

The stack's single object store is **SeaweedFS `chrislusf/seaweedfs:3.80`**
(`weed server -s3`: master + volume + filer + S3 in one binary). It replaced
MinIO — license-clean (no AGPL) and strictly better on the presigned-host axis
Delta Sharing depends on (§2.2). Reachable at `http://seaweedfs:8333` in-network,
`http://localhost:8333` from the host.

## Why 3.80 (not 4.x) — the credential-vending vs conditional-PUT tradeoff

This is a **deliberate pin** (PR #13 / Phase 2, measured on 4.00 / 4.30 / 4.40):

- SeaweedFS **4.x enforces `X-Amz-Security-Token` validation** and rejects any
  request carrying a session token that isn't a valid STS token, with
  `403 InvalidAccessKeyId`.
- **UC OSS credential vending always sends a session token** and *requires*
  `s3.sessionToken.0` to be non-empty (§2.5) — the stack uses the placeholder
  `not_used`. On 4.x that placeholder is rejected, which **breaks the primary
  UC-registered write path** (sdp-medallion, every UC table write). `-s3.iam=false`
  does not disable this; emptying UC's session token makes UC skip the bucket.
- **3.80 ignores the token**, so UC writes work.
- **Cost:** 3.80 does **not** enforce conditional PUT `If-None-Match: *` (row S-04);
  4.x does. Conditional PUT only matters for **concurrent multi-writer** Delta
  commits — which the single-writer local stack never performs — so the pin is
  correct. `test-s3-conformance.py` reports S-04 as a **KNOWN-LIMITATION**, not a
  failure. Revisit when UC OSS or SeaweedFS resolves the token conflict.

## Auth / identities

- Bare `weed server -s3` allows **anonymous** access. With `-s3.config=/…/s3conf.json`
  it correctly `403`s unsigned requests (row S-10). The stack generates
  `s3conf.json` in the container from `S3_ACCESS_KEY`/`S3_SECRET_KEY` with actions
  `["Admin","Read","Write","List","Tagging"]`.
- Clients use **path-style + SigV4** (`addressing_style=path`, `signature_version=s3v4`).
  Path-style is SeaweedFS's default (the community claim that it "expects
  virtual-hosted-style" is wrong); virtual-hosted is opt-in via `-s3.domainName`.

## Port map

| Port | Service | Notes |
|---|---|---|
| 8333 | S3 API | host-facing; published |
| 9333 | master | healthcheck probes this (IPv4 `127.0.0.1`, not `localhost`) |
| 8888 | filer | one off Jupyter's 8889 — publish deliberately |
| 8080 | volume | container-internal (also UC's container port) |

## Presigned host-rewrite (the Delta Sharing advantage, §2.2)

The sharing proxy signs a presigned URL for a **public tunnel host** while the
request lands on the **local** store. SigV4 covers `host`, so the backend's
host-verification decides success. SeaweedFS accepts **two** delivery modes
(MinIO only one):

| Mode | Delivery | SeaweedFS | MinIO |
|---|---|---|---|
| A | naive host swap, no forwarding headers | 403 | 403 |
| B | `X-Forwarded-Host` + `X-Forwarded-Proto` | **200** | 403 |
| C | `Host:` header override | 200 | 200 |

SeaweedFS's `extractHostHeaderCandidates()` / `replaceSignedHostHeader()`
(`weed/s3api/auth_signature_v4.go`) retry verification against `X-Forwarded-Host`
before falling back to `r.Host`. Locked in by
`scripts/connectivity/test-presigned-host-rewrite.py` (S-07 mode B, S-08 mode C).

## The one real S3 incompatibility (§2.3)

SeaweedFS cannot hold an object at key `x` **and** a prefix `x/` simultaneously
("same path for a file and a folder — No") — the collision surfaces as
`InternalError`. Standard Delta/Iceberg layouts never do this. Guard: the
warehouse-layout lint `scripts/connectivity/test-warehouse-layout.py` (S-09)
fails if any object key is a strict `/`-boundary prefix of another. Also: `HEAD`
on a prefix returns 200 (a dir marker), where MinIO 404s.

## What works (measured on 3.80)

- Presigned GET (SigV4 path-style), range GET, ListObjectsV2 + delimiter
  (`CommonPrefixes`), multipart ≥5 MiB, anonymous-denied — all pass.
- **Bulk / multi-object delete** works (row S-06, and a Spark `VACUUM RETAIN 0
  HOURS`), so `fs.s3a.multiobjectdelete.enable` stays at its default (true) — the
  old `…=false` was stale caution (T-2.6).
- Keep `fs.s3a.directory.marker.retention keep`: the Hadoop FileOutputCommitter's
  marker cleanup can still 500 (Delta commits via `_delta_log`, so it's unaffected).
- **Conditional PUT `If-None-Match: *` is NOT enforced** (see the tradeoff above).

## Gotchas

- **Colima bind-mount:** bind-mounting `/tmp/...` into the container silently
  fails (`fail to read /conf/s3conf.json`). Use **named volumes** or write config
  inside the container (the stack generates `s3conf.json` in-container).
- **UC credential-vending quirks** (see [[unity-catalog-oss]]): `s3.bucketPath.0`
  must be the **bucket root** (`s3://lakehouse`), not a sub-prefix; `s3.sessionToken.0`
  must be **non-empty** or `ServerProperties.getS3Configurations()` silently skips
  the bucket and vending fails with "S3 bucket configuration not found." (This same
  non-empty token is what SeaweedFS 4.x rejects — hence the 3.80 pin.)
- UC stores table `LOCATION`s as `s3://` (no `a`); Spark maps `fs.s3.impl` →
  `S3AFileSystem` so both schemes resolve to SeaweedFS.

## When something's wrong

`./lakehouse logs seaweedfs` shows the server stdout. `./lakehouse test` runs the
S3 conformance + host-rewrite + layout checks (section 2b). Anonymous 403 but
signed 403 too → check the `s3conf.json` credentials match `.env`.
