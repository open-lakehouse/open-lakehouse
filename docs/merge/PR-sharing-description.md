# PR — Delta Sharing (Phase 4)

Adds **Delta Sharing** to the stack: the OpenSharing reference server plus a
`url-rewriter-proxy` that re-signs its presigned URLs for SeaweedFS, wired in as
an opt-in `./lakehouse share` command. Ported from the containerized lakehouse
platform and adapted to open-lakehouse (SeaweedFS, the `lakehouse` bucket,
Connect-first).

Base: `feat/net-bridge-conversion` (PR #13) @ `f72ff2f` — a sibling in the CP
feature fan (`docs/merge/PR-fan-strategy.md`), not based on any other feature PR.
Purely additive: no existing service changes behavior.

## What's in it

- **`docker/delta-sharing/`** — the OpenSharing server + `url-rewriter-proxy.py`
  + configs, imported verbatim (commit 1, `Co-authored-by` the CP authors) then
  repointed to SeaweedFS (commit 2).
- **`docker-compose-sharing.yml`** — the `delta-sharing` service on the shared
  bridge network, HTTPS **8443** bound to `127.0.0.1` by default (D6).
- **`./lakehouse share`** — `seed | start | stop | status | profile`; an opt-in
  command, deliberately **not** part of `start all`. Minimal `status --json`
  (`delta_sharing`), help, and port additions only.
- **`scripts/sharing/seed_shared_tables.py`** — a self-contained seed writing two
  path-based Delta tables to fixed prefixes, so the demo is verifiable in isolation.
- **`tests/test_sharing_config.py`** — static proxy checks, SeaweedFS-repoint
  guards, and the re-sign logic exercised offline. **`.claude/skills/delta-sharing/`.**

## The interesting part — why a re-signing proxy (T-4.8)

The OpenSharing server generates the presigned S3 URLs clients fetch, but has an
**upstream bug**: `CloudFileSigner.scala` constructs `S3ClientCreationParameters()`
empty, so Hadoop's factory ignores `fs.s3a.endpoint` and always signs for
`s3.amazonaws.com` — breaking every S3-compatible store. Upstream
`delta-io/delta-sharing#753`; the 7-line fix PR `#965` is stalled awaiting review.

The proxy is the sanctioned workaround: it intercepts the server's JSON responses
and computes a **fresh SigV4 signature** for the real endpoint (a naive host swap
would invalidate the signature, since SigV4 covers `host`). This reconciles with
PR #13's SeaweedFS presigned host-rewrite contract (`seaweedfs-ops` §2.2): for the
local path the signed host equals the delivered host (plain SigV4); for a public
tunnel, SeaweedFS verifies via modes B/C. Full rationale in the `delta-sharing` skill.

## Blast radius

**Additive / new:** `docker/delta-sharing/`, `docker-compose-sharing.yml`,
`scripts/sharing/`, `tests/test_sharing_config.py`, `.claude/skills/delta-sharing/`,
a Phase-4 `PROVENANCE.md` section.

**Shared files touched (minimal, additive):** `lakehouse` (a `share` command +
`cmd_share`, a `delta_sharing` status entry, help/port lines — no existing arm
changed), `.gitignore` (ignore the token-bearing `lakehouse.share` profile). The
big doc rewrite stays in the Docs/CI PR (Phase 7).

**Reset-engine integration (additive).** Because Delta Sharing reads
`warehouse/sharing/`, `reset` now quiesces it: `reset_quiesce` stops sharing on
data/metadata/all, and it is restarted on success via `share_restore` (reuse the
existing token, `up -d` only — no re-mint, no rebuild). `cmd_stop` gains an
internal `sharing)` arm for this; sharing stays out of `start all` / `stop all`,
and `delta-sharing-certs` is a `never`-reset volume. A `tests/overlays/
docker-compose-sharing.test.yml` + `OVERLAY_BASE_SERVICES` entry keep the test
overlay renderer happy.

**Security posture (D6):** 8443 binds to loopback by default; the bearer token is
minted host-side (never a token the host can't know); the self-signed cert is a
documented local caveat for clients; no cross-file `depends_on` (the CLI sequences
storage).

## Verification

Verified live on a **fresh image build** (coursier/Maven + pip via a build-arg
package proxy; the 2.77 GB image builds clean), on the Composed stack:

- `tests/test_sharing_config.py`: **11 passed** (offline — the re-sign logic,
  repoint guards, and CLI wiring).
- **Seed:** 5 + 7 rows, re-run idempotent, `_delta_log` + parquet in SeaweedFS at
  both prefixes.
- **`./lakehouse share start`** → server healthy on HTTPS 8443; profile written.
- **Delta Sharing REST protocol end-to-end:** `shares` → `schemas` → `tables` →
  `query`. The query's `file.url` entries point at `localhost:8333` (SeaweedFS),
  **not** `s3.amazonaws.com` — i.e. the proxy re-signed them with a fresh
  `X-Amz-Credential=lakehouse_s3` SigV4 signature (the T-4.8 workaround).
- **Re-signed presigned GET → HTTP 200** with real parquet (`PAR1`) from SeaweedFS:
  the fresh signature verifies against the local store.
- **`./lakehouse share stop`** tears the service down cleanly.
- **Re-verified from a full cold teardown** — `stop all` + `stop storage` (all
  containers down, volumes preserved) → `start storage` + `start spark` →
  `share seed` → `share start` → REST + presigned GET (HTTP 200) → `share stop`,
  all driven through the committed CLI.

### External (delta-format) consumer — verified

The external consumer path was verified end-to-end. With the sharing API and
SeaweedFS reachable at a public HTTPS endpoint (`S3_PUBLIC_ENDPOINT` = that host,
`S3_PUBLIC_SCHEME=https`), a Delta Sharing client (e.g. Databricks) can:

- Register the share as a provider (TOKEN auth) from the profile; list shares →
  schemas → tables; create a catalog from the share.
- `SELECT` **all rows** of `sales_by_region` — the client reads the delta-format
  metadata, receives URLs re-signed for the public endpoint, and fetches the
  parquet through it. This exercises the **modes-B/C** delivery with a live
  external reader (previously only S3-layer-tested by #13's
  `test-presigned-host-rewrite.py`).

**Required for delta-format consumers:** the shared table must carry a checkpoint
(`_last_checkpoint`). A delta-format client (e.g. Databricks) sends
`responseformat=delta`, and the server's Delta Kernel reader treats a missing
checkpoint as fatal; a fresh single-commit table has none. The seed forces one
(`delta.checkpointInterval=1` + a second commit). External exposure is opt-in —
local sharing needs none, and a self-signed `localhost` endpoint can't be reached
or trusted by a remote consumer.

## Known issues / follow-ups

- **Self-signed cert.** Delta Sharing clients must trust it or skip TLS
  verification; a proper cert / a documented trust step is a follow-up.
- **T-4.8 is upstream-unresolved** (verified 2026-08-22: `delta-io/delta-sharing#753`
  OPEN; fix PR `#965` OPEN/unmerged, last activity 2026-06-25). The proxy is
  required until `#965` lands; then it could be dropped and the server pointed
  straight at SeaweedFS.
- **Build needs a package proxy** in restricted networks — the image build honors
  `MAVEN_REPO_URL` / `PIP_INDEX_URL` build-args (public defaults committed).
- **Delta Sharing notebooks (T-5.4)** fold into `demos/delta-sharing/` after this
  PR and the Demos PR both merge.

---

This pull request and its description were written by Isaac.
