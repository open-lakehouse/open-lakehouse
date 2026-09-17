# Stop runbook

Goal: bring everything down cleanly, and know exactly what survives.

## Default — quick stop (preserves what is on a mounted volume)

```bash
./lakehouse stop all            # Spark + Kafka ONLY
./lakehouse stop storage        # PostgreSQL + SeaweedFS (NOT included in `stop all`)
./lakehouse stop unity-catalog
./lakehouse stop airflow
./lakehouse stop mlflow
```

> **Asymmetry to know:** `./lakehouse start all` brings storage up first, but
> `./lakehouse stop all` stops only Spark + Kafka — it deliberately leaves the
> storage services (and their volumes) running so a subsequent `start` inherits a
> warm metastore/object store. Stop storage explicitly with `./lakehouse stop
> storage` when you want it down.

This runs `docker compose down` for each compose file. Containers are removed but
**all persistent state survives a restart**, because it lives in named volumes and
the Composed `postgres` service (PR #13):
- databases (UC / MLflow / Airflow / `iceberg_catalog`) → `postgres-data`;
- object data (every Delta table, MLflow artifacts) → `seaweedfs-data`;
- UC's embedded H2 catalog → `uc-data` (now **mounted**, see
  `docker-compose-unity-catalog.yml` — UC metadata persists across a plain stop);
- MLflow local state → `mlflow-data`; Spark event logs → `spark-data`.

Plain `down` (no `-v`) removes only containers and networks; none of the above is lost.

To restart later, follow [start.md](start.md) from Step 3.

## Start fresh — use `./lakehouse reset`, not `down -v`

When the user asks to "reset", "clean up", or "start fresh", use the reset command — it
confirms, supports `--dry-run`, and resets the databases + object store **surgically**.
**Do NOT use `docker compose down -v`.** Since storage is Composed (PR #13), `-v` now
**wipes `postgres-data`, `seaweedfs-data`, and `uc-data`** — i.e. every database, all
object data, and the UC catalog — in one unconfirmed, unrecoverable step. `reset` is the
safe, granular alternative (and it can preserve MLflow, dry-run, and back up first).

```bash
./lakehouse reset --all --dry-run     # preview every target, destroys nothing
./lakehouse reset --all               # confirm interactively (or --yes)
./lakehouse reset --data              # object store + dangling catalog/tracking rows
./lakehouse reset --metadata          # catalog/tracking databases (UC + airflow + iceberg + mlflow)
./lakehouse reset --metadata --keep-mlflow   # ... but preserve MLflow
```

Back up first if the state matters (see [demo.md](demo.md) for the backup/restore flow):

```bash
./lakehouse backup                    # pg_dump every DB + S3 sync + volumes + UC H2
./lakehouse restore --from <path>     # fail-stop, recoverable
```

After a reset, run `./lakehouse doctor` to confirm no orphaned data or catalog
inconsistencies remain.

## Why raw `docker compose down -v` is the wrong tool here

`-v` removes **Compose-managed named volumes**. Since storage moved into Compose (PR #13),
those volumes now hold **everything**, so `-v` is far more destructive than it used to be:

- wipes **`postgres-data`** — every database (UC / MLflow / Airflow / `iceberg_catalog`), so
  all catalog and tracking metadata is gone;
- wipes **`seaweedfs-data`** — the whole object store, i.e. every Delta/Iceberg file under
  `s3://lakehouse/warehouse/` and all MLflow artifacts;
- wipes **`uc-data`** (UC's embedded H2 store), **`mlflow-data`**, and **`spark-data`** too.

Before PR #13 storage was host-installed and out of `-v`'s reach, so `-v` could only reach a
subset and produced a **half-wiped, internally inconsistent** environment. Now it destroys
the lot in one unconfirmed, unrecoverable step. Either way, `down -v` is the wrong tool:
`./lakehouse reset` (confirms, `--dry-run`, backs up, granular `--data`/`--metadata`) is the
right one. Never reach for `down -v` to "start fresh".

## Verifying nothing is left running

```bash
docker ps --filter "name=spark-\|name=kafka\|name=zookeeper\|name=unity-catalog\|name=airflow\|name=mlflow"
```

Should return an empty list.

## Restart vs stop+start

For config changes that need a fresh container:

```bash
./lakehouse restart spark   # equivalent to stop + 2s sleep + start
```

For Java heap or JAR changes, prefer full stop + start (`restart` reuses the same compose
project state).
