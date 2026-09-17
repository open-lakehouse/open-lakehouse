# PR #13 — review handoff (for the implementing agent)

**No code in this file.** Actionable findings only. Apply fixes on `feat/net-bridge-conversion`. Do not open or push a GitHub PR until P0–P1 below are done unless a human says otherwise.

| | |
|---|---|
| Branch | `feat/net-bridge-conversion` |
| Diff base | `feat/merge-cp-integration` (`main` + PR #11 + PR #12) |
| GitHub PR | none yet (local tranche only) |
| Description | `docs/merge/PR13-description.md` |
| Reviews | Grok/Cursor PR review (2026-08-20) + Bugbot rerun (2026-08-21) |

Already fixed in `da31b8c` — **do not re-do**: `start all` starts storage first; status/preflight probes storage on **fixed** 5432/8333; reset quiesces Jupyter; `postgres-data`/`seaweedfs-data` reset mode is `"never"`.

Pre-existing lifecycle items already recorded in the PR description (restore `--force` vs run-scope; `iceberg_catalog` DB vs golden rule 1) — **do not change those in this PR** unless a maintainer asks.

---

## Bugbot (2026-08-21)

Five findings. Two overlap the earlier review (`SPARK_LOCAL_IP`, `CLAUDE.md` `-v`).

| Severity | Location | Finding | Action |
|---|---|---|---|
| high | `docker-compose-spark41.yml:39` | `SPARK_LOCAL_IP=$(hostname -i \| cut -d' ' -f1)` can pick `127.0.1.1` first. Master/worker/Connect then advertise loopback; RPC fails. ECS helper skips `127.*`. | Port `hostname -i \| tr ' ' '\n' \| grep -vE '^127\.' \| head -1` (see `terraform/spark-ecs/docker/entrypoint.sh`). Apply to master, worker, **and** Connect. Overlay worker/connect commands must keep the same snippet (see P0.2). |
| high | `CLAUDE.md:21` | Golden rule 4 still says `docker compose down -v` cannot reset host PostgreSQL/SeaweedFS. Both are Compose volumes now. | Rewrite GR#4 to match `.claude/skills/lakehouse-lifecycle/SKILL.md` rule 5: `-v` wipes `postgres-data`, `seaweedfs-data`, `uc-data`, etc. Cheat sheet: `start all` now starts storage. |
| medium | `lakehouse:164` | `preflight_checks` still uses host `psql`. `./lakehouse test` already uses `pg_psql`. | Use `pg_psql` (or equivalent dockerized client) in preflight. |
| medium | `lakehouse:157` | Preflight requires live Postgres + SeaweedFS **before** start. Cold `./lakehouse preflight` fails even though `start storage` is the bootstrap. | Do not require storage to be up for a cold preflight; probe ports-free / Docker / `.env` / JARs instead, or treat “storage not running yet” as OK with a hint to `start storage`. |
| medium | `lakehouse:712` | `init-storage.sh` needs host `aws`. On failure the CLI **warns and continues**. | Fail `start storage` / `start all` if init fails. Prefer a dockerized `aws` if host CLI is missing (same pattern as `pg_psql`). |

---

## P0 — must fix (overlay + agent map)

### 1. Always-loaded agent map is wrong about `-v`

`CLAUDE.md` GR#4 (and any leftover “host-installed” / “can’t reset host PostgreSQL” lines in `.claude/skills/lakehouse-lifecycle/stop.md`, `demo.md`). Lifecycle **SKILL.md** rule 5 is already correct — make `CLAUDE.md` and the runbooks match it.

Also: `./lakehouse start all` starts storage; `./lakehouse stop all` does **not** stop storage (only `stop storage` does). Document that asymmetry or include storage in `stop all` if that was the intent.

### 2. Test overlays were not converted with the base files

`overlay_set_compose_args` **requires** `docker-compose-<svc>.test.yml` whenever overlay mode is active. There is **no** `docker-compose-storage.test.yml`, and `OVERLAY_BASE_SERVICES` omits `storage`. Under overlay:

- `./lakehouse start storage` / `stop storage` / `start all` (storage arm first) fail with “required overlay file missing”
- `tests/integration/conftest.py` `composed_storage` inherits overlay env if set, **ignores the start RC**, then tests skip or hit whatever is on 5432

Storage is unscoped and always on 5432/8333 (intentional). Then `overlay_set_compose_args storage` must use **only** the base file (no overlay required).

**Kafka overlay** (`tests/overlays/docker-compose-kafka.test.yml`) still sets `KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-${SUFFIX}:9092`. Base now uses `INTERNAL`/`EXTERNAL`. Overlay Kafka likely cannot start. Set overlay advertised to `INTERNAL://kafka-${SUFFIX}:9092` (drop or remap EXTERNAL if unpublished).

**Spark overlay** replaces worker/connect `command` and **drops** `SPARK_LOCAL_IP`. That reintroduces advertise-loopback on the E-07 path. Keep the same IP snippet as the base file; keep `spark://spark-master-41-${SUFFIX}:7078`.

Rewrite `tests/overlays/README.md`: Postgres/SeaweedFS are **not** host-installed. Storage is shared Compose on published ports; overlays reach it via `host.docker.internal` on purpose.

### 3. U-17 reads a gitignored file

`tests/test_storage_config.py` asserts on `config/unity-catalog/server.properties` (`.gitignore`). Fresh CI / new clones only have `server.properties.example`. Point U-17 at the example (or copy-from-example in the test).

---

## P1 — will fail real runs / lie to the next agent

### 4. Three different S3 default credentials

| Place | Defaults |
|---|---|
| Compose / `init-storage.sh` | `admin` / `admin_password` |
| `.env.example` | `your_access_key_here` |
| `scripts/connectivity/test-s3-*.py`, lifecycle tests, **I-09 hardcode** | `lakehouse_s3` / `lakehouse_s3_secret` |

`./lakehouse test` 2b and `test_i09_mlflow_314_run_artifact_in_s3` 403 unless the developer picked the test pair. Unify one demo pair across compose defaults, `.env.example`, init-storage, and test fallbacks. I-09 must read env, not bake `lakehouse_s3`.

### 5. `docs/getting-started/configuration.md` still teaches the old topology

Networking section is updated; **Required Variables** still has `POSTGRES_HOST=host.docker.internal`, `S3_ENDPOINT=http://host.docker.internal:8333`, and `ICEBERG_CATALOG_URI=postgresql://…/iceberg_catalog`. Spark snippet still uses `localhost:8081` / `localhost:8333` as in-container config. That contradicts golden rule 1 and bind-mounted `spark-defaults` (`unity-catalog:8080`, `seaweedfs:8333`). U-15 only greps `network_mode: host` / “host networking”, so this slipped through. Remove JDBC catalog URI from “required” env.

### 6. Airflow / MLflow do not wait for Compose Postgres

- `docker-compose-airflow.yml`: `airflow-init` has `depends_on: []` and no postgres wait.
- `docker-compose-mlflow.yml`: no `depends_on: postgres`.

`start mlflow` / `start airflow` without storage already up crash-loop. Add `depends_on` with `service_healthy` (postgres healthcheck already exists). `wait_for_service` for storage is only `nc -z` 5432 — prefer `pg_isready` via `pg_psql` / docker exec.

---

## P2 — demo / comments (do not churn the happy path)

- `demos/sdp-medallion/run.sh`: `pip install … || true`, `grep seed complete || true`, and `docker stop spark-connect-41`. Seed/dep failures are silent; Connect stays down on SIGKILL. SDP golden rule: do not disable Connect. Restore Connect on abort; do not `|| true` the seed.
- `docker-compose-notebooks.yml` header still says “no token required” (D5 requires a token). `/api` healthcheck is fine.
- UC compose comment still shows `spark.sql.catalog.iceberg.uri = http://localhost:8080` (wrong host port and wrong in-network name).
- `postgres:16` is unpinned (SeaweedFS is pinned 3.80). Optional: pin a minor if you care about reproducibility.

---

## Do not churn (looks correct)

- Official UC `unitycatalog/unitycatalog:v0.5.0`, Delta 4.3.1 + connector 0.4.1 / client 0.5.1 / hadoop 0.5.1, SeaweedFS **3.80** pin + session-token/4.x write-up.
- Production Kafka dual listeners (`INTERNAL://kafka:9092`, `EXTERNAL://localhost:9092` via `9092:19092`).
- SeaweedFS healthcheck on `127.0.0.1:9333`.
- Jupyter empty-token → unset → mint random.
- `uc-data` mounted; `init-storage.sh` `docker exec` for DBs.
- S-04 as KNOWN-LIMITATION on 3.80.

---

## Suggested order

1. `CLAUDE.md` GR#4 + cheat sheet + leftover host-installed lines in lifecycle runbooks; preflight cold-start + host `psql`.
2. Special-case storage in `overlay_set_compose_args`; fix Kafka + Spark overlay commands + IP filter on base Spark; rewrite overlay README.
3. Unify S3 creds; point U-17 at `.example`; repair `configuration.md`.
4. Fail start on init-storage failure (dockerize `aws` if needed); postgres `depends_on` for Airflow init + MLflow.
5. Tighten `run.sh`; stale compose comments.

After fixes: unit tests for overlay render (Kafka advertised listener names, Spark overlay still exports non-loopback `SPARK_LOCAL_IP`, `start storage` under overlay env does not require a missing overlay file) plus a cold `./lakehouse preflight` that must not demand live storage.
