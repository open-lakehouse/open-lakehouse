# PR #13 — Network + storage foundation (Phases 1 + 2)

Converts the local stack from host-networking + host-installed storage to
**bridge networking + storage-in-Compose**, upgrades the version-pinned
components that the merge depends on, and adds the SeaweedFS S3 conformance
suite. This is the only tranche of the CP merge that changes existing local
workflows; it is independently defensible via open-lakehouse's own `SECURITY.md`
and lands before the additive feature PRs sit on top.

Base: `main` + PR #11 (demos/mlflow uv.lock hygiene) + PR #12 (lifecycle/reset
safety). See `docs/merge/PROVENANCE.md` for exact SHAs, `docs/merge/DECISIONS.md`
for the D1–D8 pointer.

## What's in it

**Phase 1 — bridge + storage + versions**
- **Bridge networking (D1).** Every service moves off `network_mode: host` onto
  the shared `lakehouse-network`; peers are addressed by service name; host-facing
  services publish ports. Spark ports the `spark-ecs` advertise-address pattern
  (master advertises its own bridge IP, never `0.0.0.0`). `sc://localhost:15002`
  is preserved (I-03).
- **Storage in Compose.** PostgreSQL 16 and SeaweedFS become Compose services
  with named volumes (`docker-compose-storage.yml`); `./lakehouse start storage`
  bootstraps the bucket, warehouse prefixes, and `iceberg_catalog`.
- **UC → official `unitycatalog/unitycatalog:v0.5.0` (D2).** Replaces the
  personal pre-publish staging image (supply-chain hygiene). Non-breaking (I-44);
  unlocks **catalog-managed Delta** (I-45).
- **Delta → 4.3.1 + the UC 0.5.x Spark connector family** (connector 0.4.1 +
  client 0.5.1 + hadoop 0.5.1) — the exact set that makes catalog-managed Delta
  work (I-02/I-45). 4.3.0 alone NPEs through the connector.
- **MLflow → 3.14** (I-09) + healthcheck fix (the image has no `curl`).
- **Jupyter token auth (D5)** + spark-pipelines deps in the image.
- **sdp-medallion** made coherent and runnable end-to-end on catalog-managed
  Delta (self-contained `seed.py` + one-command `run.sh`).

**Phase 2 — SeaweedFS hardening & S3 conformance**
- S3 conformance matrix, presigned host-rewrite (modes B + C — SeaweedFS's Delta
  Sharing edge over MinIO), and a warehouse-layout lint, all wired into
  `./lakehouse test` (`scripts/connectivity/test-s3-*.py`).
- Removed the stale `fs.s3a.multiobjectdelete.enable false` (bulk delete works).
- New `seaweedfs-ops` skill.

## Blast radius

**Breaks / changes behavior**
- The `localhost:9092` / `localhost:8081` **in-container idiom** — in-network
  clients now use service names (`kafka:9092`, `unity-catalog:8080`, …); the host
  still uses `localhost:<published-port>`. Any local scratch work assuming host
  networking needs updating.
- **Host-installed SeaweedFS / PostgreSQL → Compose services + named volumes.**
  Needs the migration note (`docs/merge/MIGRATION.md`, E-06). Host setups often
  kept data in disposable locations (`/tmp/seaweedfs`), so most users start clean.
- **UC image `newfrontdocker/…:v0.4.1` → official `…:v0.5.0` (D2).** The
  `unity-catalog-oss` / `sdp` skills are valid only after the T-1.18 review — do
  **not** claim "UC unchanged." UC 0.5.0's `/tables` API is also stricter (a
  column's `type_json` must be a real descriptor, not `{}`).
- **Jupyter's empty token is removed; token auth required (D5).**
- **`docker compose down -v` can now destroy object data *and* metadata (R-15)** —
  it wipes `postgres-data`, `seaweedfs-data`, `uc-data`. Mitigated by PR #12's
  `./lakehouse reset` (and `stop` without `-v`), after the lifecycle re-ground.

**Explicitly unaffected**
- `sc://localhost:15002` (I-03 / Golden Rule #3).
- AWS / Terraform `awsvpc` — independent of local Compose (E-05).
- The Iceberg **write** story — still upstream-blocked in every UC OSS build;
  I-47 pins it. **No "format neutrality restored" claim.** Reads stay
  engine-neutral via the Iceberg REST endpoint.
- No conflicting unmerged branches beyond #11 / #12.

## Known issues / follow-ups

- **SeaweedFS pinned at 3.80, not 4.x** (deliberate — `docs/merge/` +
  `seaweedfs-ops`). SeaweedFS 4.x enforces `X-Amz-Security-Token` validation and
  rejects UC OSS credential vending's *mandatory* placeholder session token
  (403), breaking the primary UC write path (measured 4.00/4.30/4.40). 4.x fixes
  conditional PUT (`If-None-Match: *`, row **S-04**), so on 3.80 that row is a
  documented **KNOWN-LIMITATION** — it matters only for concurrent multi-writer
  Delta commits, which the local single-writer stack never does. Revisit when UC
  OSS stops requiring a vended token or SeaweedFS adds a static-cred-with-token
  path.
- **`reset` does not wipe Kafka topics / checkpoints** — the honest `--dry-run`
  says so. Follow-up (schedule as an immediate #14 or within #13).
- UC Spark connector `0.5.0` is not published (only `0.4.1`); catalog-managed
  Delta relies on connector 0.4.1 + client/hadoop 0.5.1. Track a 0.5.x connector.

### Maintainer notes — pre-existing lifecycle semantics (PR #12), flagged not changed

A code-review pass raised two items in the reset/restore engine that predate this
PR (they live in the PR #12 lifecycle code). They are **intentional PR #12
semantics**, not PR #13 regressions, so this PR leaves them as-is and records them
for a maintainer decision rather than changing lifecycle behavior here:

- **`restore --force` escapes the run-scope guarantee.** `restore_apply` mutates
  the targets read from the backup MANIFEST (bucket / databases / volumes), and
  the run-scope reconciliation lives in `restore_validate_targets`, which `--force`
  skips. `reset_semantic_gate` validates the *current* run's effective targets but
  never inspects MANIFEST names — so under an active overlay,
  `restore --from <other-run-artifact> --force` passes the gate and then drives
  `pg_restore --create --clean` + `s3 sync --delete` against another run's
  resources. `--force` is a documented, deliberate "discard safety" override (its
  purpose is to bypass the reconciliation), but it silently also escapes run
  isolation. If run-scoping should hold even under `--force`, the gate would need
  to validate the MANIFEST names, not just the current run's.

- **`iceberg_catalog` PostgreSQL DB vs. golden rule #1.** `init-storage.sh`
  provisions an `iceberg_catalog` database and `reset` drops/recreates it and runs
  `DELETE FROM iceberg_tables` — the shape of an Iceberg JDBC catalog — while
  CLAUDE.md golden rule #1 says "no PostgreSQL JDBC catalog path exists." This is
  the PR #12 reset **target matrix** (§1.13.4) treating `iceberg_catalog` as a
  resettable database, not a live Spark catalog binding, so the two don't strictly
  contradict — but the naming invites confusion and should be reconciled (either
  rename/annotate the reset target, or clarify the rule to mean "no JDBC catalog on
  the Spark read/write path").

### Review fixes applied on this branch (lifecycle-engine findings)

A later `/code-review` pass surfaced defects in the reset/backup/lifecycle engine. These
are fixed **here on `feat/net-bridge-conversion`** (the live trunk the demo/feature fan
stacks on) rather than cascaded through the owner-controlled PR #12 →
`feat/merge-cp-integration` → this branch. Most originate in PR #12's lifecycle code
(`git blame`: reset engine `12afac8`, backup/restore engine `eac890d`); the notebooks
start/stop asymmetry originates here in PR #13 (`da31b8c` added `stop notebooks` with no
matching `start`). **They can be cherry-picked onto PR #12** if the owner prefers them on
the standalone lifecycle PR.

- **Backup/restore no longer wipe the live storage volumes (HIGH).** `backup_take_snapshot`
  / `restore_apply` swept in `postgres-data` / `seaweedfs-data`, whose services stay live
  (excluded from `backup_writer_containers`), so a restore ran `rm -rf` + tar over the running
  metastore/object store. Both now skip `reset_volume_mode == "never"` volumes (backup by base
  name; restore by effective/project-prefixed name, as the MANIFEST stores them); their content
  is captured/restored via `pg_dump` + `s3 sync`. (Origin PR #12 `eac890d`; the bug only
  manifested once PR #13 moved storage into Compose.)
- **`start notebooks` + Jupyter-after-reset.** `cmd_start` gained a `notebooks` arm (opt-in,
  not in `start all`), and `reset_running_services` now restarts a previously-running Jupyter.
  (Asymmetry origin PR #13 `da31b8c`; the reset half PR #12 `12afac8`.)
- **aws-cli pinned.** The reset/backup dockerized aws-cli defaulted to `:latest`; pinned to
  `2.24.6` (still `LAKEHOUSE_AWSCLI_IMAGE`-overridable), matching `init-storage.sh` /
  `demos/_lib`. (Origin PR #12.)
- **`reset --data` residual check — left as-is, intentionally.** The review flagged that the
  post-delete residual-key count could fail on SeaweedFS directory markers. Measured: a
  torn-down prefix shows **0 objects** via S3 `ListObjects` (SeaweedFS filer directories are not
  S3-visible), so the count-based fail-stop is not tripped by them. A visible undeletable marker
  only arises from a raw FileOutputCommitter `_temporary/` object, which this stack's Delta
  writes avoid — so the safety fail-stop is **not weakened**.

Regression tests for the applied fixes: `tests/test_pr13_review_fixes.py`
(`TestBackupRestoreSkipStorageVolumes`, `TestNotebooksLifecycle`, `TestAwsCliPinned`).

## Verification

See the "before PR #13 leaves draft" gate report in the session log: 183 unit
tests + the S3 conformance (S-01…S-11), version/D2 gates (I-02/08/09/12/44/45/47),
neutrality guards (U-15/17/22/35/36/40, I-42), and the re-grounded lifecycle
regression (E-07 + I-28/29/30) on the Composed topology. `sc://localhost:15002`,
distributed Spark execution, and the sdp-medallion demo all verified on a fresh
teardown + rebuild.

Re-verified after the review fixes on a **full teardown → fresh rebuild** (no
`-v`; data volumes preserved): storage → Spark → Kafka → Unity Catalog → MLflow
all came up healthy (`status --json` → `all_healthy: true`), the new
`pg_isready` gate fired for storage/MLflow, and `init-storage` bootstrapped
idempotently against unscoped `postgres`/`seaweedfs`. `./lakehouse test` is green
(S-01…S-11, with **S-04** the documented known-limitation), and the full
`pytest tests/` run is **262 passed / 56 skipped**.

**Known-environmental (not PR regressions), so not blocking:**

- **JVM-dependent local-Spark integration tests are environment-skipped here.** A
  tier of `tests/integration/` tests builds an *in-process* Spark
  (`.master("local[2]")`) against a temp `hadoop`-type Iceberg catalog. Those
  need a **host JDK**, which this box lacks (the stack is Connect-first and runs
  Spark in Docker), so they error at fixture setup rather than run. They exercise
  local-mode Spark + a filesystem catalog — **not** the Connect/UC/SeaweedFS path
  this PR changes — so they carry no signal for it. Follow-up (hygiene, not this
  PR): guard them with `skipif(no host JVM)` so they skip cleanly, or rewire them
  onto `sc://localhost:15002` + the UC catalog.
- **Airflow is not built/run in this sandbox.** `docker/airflow/Dockerfile` lacks
  the overridable `ARG PIP_INDEX_URL` the repo convention uses, so its build can't
  reach the package proxy and hits blocked public PyPI. Pre-existing; this PR does
  not touch `docker-compose-airflow.yml` (its only Airflow change is the CLI
  `pg_isready` gate, which runs before the build step). Airflow was not running
  before the teardown either.
- A handful of stale integration tests are red independent of this work (an
  airflow `network_mode: host` assertion from before the bridge conversion, moved
  script paths, `admin/admin` hardcoded S3 creds, missing DAG files). Batched with
  the deferred doc/test hygiene, not fixed here.

---

This pull request and its description were written by Isaac.
