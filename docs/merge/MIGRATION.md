# Migration guide — PR #13 (network + storage foundation)

PR #13 changes how the local stack is networked and where its state lives. This
guide is for anyone with an **existing** open-lakehouse checkout who pulls these
changes. New users can ignore it — a fresh `./lakehouse setup && ./lakehouse
start …` already does the right thing.

## What changed

| Area | Before | After (PR #13) |
|------|--------|----------------|
| Networking | `network_mode: host` — services on `localhost` | Shared **bridge** `lakehouse-network`; peers by service name, host via published ports |
| PostgreSQL | host-installed | **Compose service** `postgres`, data in the `postgres-data` named volume |
| SeaweedFS (S3) | host-installed (data often in `/tmp/seaweedfs`) | **Compose service** `seaweedfs` (pinned **3.80**), data in `seaweedfs-data` |
| Unity Catalog | `newfrontdocker/unitycatalog:v0.4.1` (staging image), H2 in the container layer | official **`unitycatalog/unitycatalog:v0.5.0`**, H2 on the **mounted `uc-data`** volume (survives a plain stop) |
| MLflow | 3.13 | **3.14** |
| Delta | 4.2.0 | **4.3.1** + the UC 0.5.x Spark connector family (connector 0.4.1 + client 0.5.1 + hadoop 0.5.1) — enables catalog-managed Delta |
| Jupyter | tokenless (XSRF off) | **token auth** (`JUPYTER_TOKEN` in `.env`) |

## Steps

1. **Stop the old stack** and, if you were running host-installed PostgreSQL /
   SeaweedFS, stop those host services (they're now Compose services and would
   collide on ports 5432 / 8333).
2. **Pull PR #13** and re-run setup so the new JARs land:
   ```bash
   ./lakehouse setup            # downloads Delta 4.3.1 + UC 0.5.x connector jars
   ```
3. **Set the new `.env` keys** (copy from `.env.example`): `JUPYTER_TOKEN` (any
   value; empty makes Jupyter mint a random token, never tokenless). The S3 /
   Postgres creds now describe the Compose services — `localhost` host addresses,
   service-name addresses in-container are wired for you.
4. **Bring it up** and bootstrap storage:
   ```bash
   ./lakehouse start storage    # starts postgres + seaweedfs, creates bucket + prefixes + iceberg_catalog
   ./lakehouse start all
   ./lakehouse start unity-catalog
   ./lakehouse start mlflow
   ```
5. **Migrate existing data (optional).** Host-installed setups typically kept
   demo data in disposable locations (`/tmp/seaweedfs`), so most users can start
   clean. If you must carry data over: copy objects into the new `seaweedfs`
   service with any S3 client against `localhost:8333`, and `pg_dump` / restore
   your old databases into the `postgres` service. There is no automatic import.

## Teardown changed — do NOT use `docker compose down -v`

This is the important one. Because storage is now **Compose-managed named
volumes**, `docker compose down -v` will **destroy everything** in one
unconfirmed step:

- `postgres-data` — UC / MLflow / Airflow / `iceberg_catalog` databases
- `seaweedfs-data` — all object data (every Delta table, MLflow artifacts)
- `uc-data` — the UC catalog (catalogs, schemas, table registrations)
- `mlflow-data`, `spark-data`

Before PR #13 (host-installed storage) `-v` could only reach a subset; now it
reaches all of it. Use the lifecycle commands instead:

```bash
./lakehouse stop            # safe: removes containers, keeps every volume
./lakehouse reset --dry-run # preview what a reset would touch (destroys nothing)
./lakehouse reset --all     # confirmed, surgical reset of DBs + object store
./lakehouse backup          # pg_dump every DB + S3 sync + volumes + UC H2, first
```

## Explicitly unaffected

- `sc://localhost:15002` — the Spark Connect client endpoint is unchanged.
- AWS / Terraform (`terraform/`) — `awsvpc` networking is independent of the
  local Compose change; nothing there is touched.
- The Iceberg **write** story — still upstream-blocked in every UC OSS build
  (Delta-write / Iceberg-read-only); this PR does not change it.
