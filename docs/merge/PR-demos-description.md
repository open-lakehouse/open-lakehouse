# Demos — five analytical demos on Spark Connect (Phase 5)

Ports five analytical notebooks from the containerized-lakehouse platform into the
`demos/` contract, rewritten for the open-lakehouse stack (Spark Connect, SeaweedFS,
Unity Catalog OSS 0.5.0, catalog-managed / external Delta). This is a **purely
additive** feature PR: it adds new demo directories (five demos + a shared `demos/_lib/`)
and touches only two pre-existing docs (`demos/README.md`, `docs/merge/PROVENANCE.md`).

Base: `feat/net-bridge-conversion` @ `4e25c6b` (PR #13, the network + storage
foundation), per the fan strategy in `docs/merge/PR-fan-strategy.md`. It does **not**
target `main` and does **not** modify any PR #13 trunk file (the `lakehouse` CLI,
`docker-compose-*.yml`, `scripts/`, `config/`).

## What's in it

Five demos, each following `demos/_template/` (script + `README.md` with verified
expected-stdout + idempotent `teardown.sh`):

| Demo | From | What it shows |
|---|---|---|
| `demos/quick-start/` | `01_Quick_Start` | First governed Delta table via the three-level namespace, query, one ACID update — the onboarding path. |
| `demos/delta-deep-dive/` | `02_Delta_Lake_Deep_Dive` | ACID `UPDATE`/`DELETE`/`MERGE`, time travel, schema evolution, `OPTIMIZE` (path-based Delta, SQL). |
| `demos/unity-catalog/` | `03_Unity_Catalog` | Three-level namespace, external Delta registration, metadata via SQL + UC REST, cross-schema join. |
| `demos/analytics/` | `04_Analytics` | Revenue / regional / window-function / daily-trend SQL on a governed table, charts to PNG. |
| `demos/mlflow-tracking/` | `05_MLflow_Tracking` | Experiment tracking, run comparison, Model Registry, a `champion` alias (sklearn models). |

Plus: `docs/merge/PROVENANCE.md` gains a "Phase 5 — Demos" attribution section
(notebook→demo mapping + reworkings), and `demos/README.md`'s "Demos in this build"
table lists the five as **Built**.

## Transport & conventions

- Connect-first: every demo uses `SparkSession.builder.remote("sc://localhost:15002")`
  (or `LAKEHOUSE_SPARK_REMOTE`), run via `poetry run python demos/<name>/<script>.py`.
- Each demo caps `spark.sql.shuffle.partitions = 8` (demo-scale data; keeps memory and
  file counts small on a local host).
- Deterministic (seeded), so the READMEs' expected-stdout snippets match a real run.
- Re-runs are safe with no teardown in between (verified run-twice for each). The **four Delta
  demos** are self-cleaning: they clear their S3 prefix and write Delta with `overwrite` (then
  register, for the UC-backed ones) at the start. **`mlflow-tracking`** writes no Delta table — it
  restores a soft-deleted experiment and registers a new model version on re-run, and its artifacts
  are removed by its teardown (not cleared at start).
- Shared plumbing lives in `demos/_lib/` (`delta_helpers.py` — `clear_prefix` /
  `recreate_delta_table`; `s3_cleanup.sh` — the `awscli` host/docker wrapper + `clear_s3_prefix`),
  imported by the scripts and sourced by the teardowns. The demo narrative stays per-demo.

## Stack-specific decisions (discovered + documented in-demo / PROVENANCE)

- **UC external tables:** `CREATE TABLE … USING delta LOCATION 's3://…'` — the `s3://`
  scheme (UC credential vending rejects `s3a://`: *Unsupported URI scheme: s3a*), and
  **not** `CREATE TABLE AS SELECT` (CTAS triggers path-credential vending that fails for
  ad-hoc locations). Location-less creates are treated as catalog-managed.
- **Deterministic re-creation on SeaweedFS:** dropping a UC table leaves the S3 data, and
  SeaweedFS retains a *filer directory entry* that S3 `DeleteObject` can't remove (S3
  `ListObjects` shows empty, but Delta's emptiness check still sees the dir → a bare
  `CREATE TABLE … LOCATION` fails `DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION`). The demos
  therefore **write the data with Delta `overwrite`** (which lays down a fresh `_delta_log`
  over the lingering dir) and then register — see `recreate_delta_table`.
- **No raw parquet writes:** plain `df.write.parquet` uses S3A's rename committer, which
  SeaweedFS does not support (*Could not rename …_temporary*); Delta's log-based commit
  works. (Why quick-start proves storage with a Delta write, not a parquet probe.)
- **MLflow uses scikit-learn, not Spark ML:** `mlflow.spark.log_model` saves the model via
  Spark writes (the same rename committer → SeaweedFS rejects it); `mlflow.sklearn.log_model`
  uploads via boto3 and works. Spark Connect still does the data sourcing / feature prep.
- **Discovery quirks:** `SHOW CATALOGS` over Connect lists only the session-default
  `spark_catalog` (UC v2 catalogs register lazily) — the UC REST API is the authoritative
  catalog list; UC 0.5.0's `/tables` omits column metadata for connector-registered external
  tables (columns come from `DESCRIBE` / the Delta log).

## Client dependencies

`matplotlib` (analytics charts) and `mlflow` + `scikit-learn` (mlflow-tracking) are
**documented `poetry run pip install …` in the demo READMEs**, deliberately **not** added
to `pyproject.toml`. A poetry optional group was the preferred design, but Poetry 2.4 can
only reach a mirror via `[[tool.poetry.source]]`, which bakes the (internal) proxy URL into
the lock and content-hash — not committable — and a proxy-only environment can't regenerate a
clean public-PyPI lock. If desired, add a `demos` group and run `poetry lock` on a
public-PyPI-reachable machine.

## Blast radius

**Additive only.** New directories under `demos/` — the five demo dirs plus `demos/_lib/`
(`delta_helpers.py` + `s3_cleanup.sh`, the shared object-store/Delta helpers the demos and
teardowns use). No behavior change to any existing service or demo. The only pre-existing files
touched are `demos/README.md` (table rows + a `_lib` note) and `docs/merge/PROVENANCE.md` (new
section). No `lakehouse` CLI, compose, `scripts/`, `pyproject.toml`, or `poetry.lock` changes, so
this merges independently of the other CP-feature PRs.

## Verification

Run on the local stack (`./lakehouse status --json` → `all_healthy` and
`spark.connect_grpc_listening: true`). For **each** demo: teardown → run → run again with no
teardown between → teardown → confirmed the S3 prefix is at **zero objects**. quick-start also
passed the explicit re-run trap (UC table dropped, S3 left behind). mlflow-tracking registers the
best run's logged-model URI (`log_model(...).model_uri`, i.e. `models:/m-<id>`) — not
`runs:/<id>/model`, which has no artifacts under MLflow 3 and would trigger the
"registering model based on models:/m-… instead" fallback — and confirmed the registered model,
experiment, and `mlflow-artifacts/<exp_id>` are all removed on teardown, with a second run
incrementing the model version (`v1` → `v2`) and champion selection isolated to that invocation.
`black --check`, `ruff check`, and `shellcheck -S warning` are
clean on all five scripts and teardowns.

The teardowns' dockerized `aws-cli` fallback (host `aws` else `amazon/aws-cli:2.24.6`,
mirroring `scripts/tools/init-storage.sh`) was not exercised here — this machine has a host
`aws`, so the host path ran; the fallback branch is structurally identical to the verified
init-storage wrapper.

## Not in this PR (deferred)

- `demos/unity-catalog-multi-engine/` (T-5.6) stays a placeholder: UC OSS 0.5.0's Iceberg REST
  endpoint cannot serve any table this stack can write (catalog-managed + UniForm is mutually
  exclusive with UC's deletion-vectors mandate; external UniForm is never registered with a
  metadata-location), so a real multi-engine-via-REST demo is a follow-up.
- The Delta Sharing notebook fold (`06`/`09`/`10`, T-5.4) waits on the Sharing PR.

## Suggested commit structure

One `feat(demos): …` commit per demo (or one for all five), each carrying `Co-authored-by`
trailers to the CP notebook authors, plus a `docs(demos): …` commit for `demos/README.md` +
`docs/merge/PROVENANCE.md`.

---

This pull request and its description were written by Isaac.
