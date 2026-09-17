---
name: lakehouse-lifecycle
description: Use when starting, stopping, demoing, or troubleshooting the open-lakehouse stack (Spark 4.1, Kafka, Airflow, Unity Catalog, MLflow). Provides deterministic start/stop/demo runbooks an AI agent can execute top-to-bottom.
---

# Lakehouse lifecycle

You are operating the open-lakehouse demo platform. Everything you need to spin services up, run a demo, and tear them down is in this directory. Read the file that matches the user's intent — don't load all of them.

## Files in this skill

| Intent | File |
|--------|------|
| Spin up services from a cold state | [start.md](start.md) |
| Bring everything down cleanly | [stop.md](stop.md) |
| Run one of the demos under `demos/` | [demo.md](demo.md) |
| A symptom is showing — diagnose | [troubleshoot.md](troubleshoot.md) |

## Companion scripts (invoke by relative path)

- `scripts/preflight.sh` — single shell script that runs port checks, .env validation, Docker reachability, and JAR presence. Exits non-zero on any blocker.
- `scripts/smoke.sh` — minimum-viable post-start verification: writes a row to an Iceberg table via Spark, lists it back via Unity Catalog REST, then drops the table.

## Golden rules (never violate)

1. **No JDBC catalog mode exists in this repo.** The Iceberg catalog is always Unity Catalog OSS reached via REST. If a config or doc references `spark.sql.catalog.iceberg.type=jdbc` or `spark.sql.catalog.iceberg.jdbc.*`, that's a bug — flag it, don't fix the symptom downstream.

2. **Spark is 4.1 only.** There is no `--version` flag. The compose file is `docker-compose-spark41.yml`. The master container is `spark-master-41`. If something asks you to start "Spark 4.0", that's a stale instruction.

3. **Connect-first transport.** The default mode is `--spark-connect`. Spark Connect server runs in the `spark-connect-41` container on port 15002. Clients connect via `SparkSession.builder.remote("sc://localhost:15002")` (or read `LAKEHOUSE_SPARK_REMOTE` from the env exported by the CLI). SDP requires Connect machinery even though `spark-pipelines` doesn't call `.remote()` explicitly — `pyspark.pipelines` uses `SparkConnectGraphElementRegistry` internally. **Don't disable the Connect server; SDP breaks without it.**

4. **`--spark-local` is a stub.** It exists on the CLI for forward-compat but exits with "not yet implemented" today. The placeholder demo lives at `demos/local-mode-spark/README.md`. Don't try to make local mode work by hand-patching — when it lands, it'll be its own clean implementation.

5. **Never destroy state with raw `docker compose down -v`.** Since storage moved
   into Compose (PR #13), `-v` now **wipes the named volumes that hold everything**:
   `postgres-data` (UC/MLflow/Airflow/iceberg_catalog databases), `seaweedfs-data`
   (all object data — every Delta table), `uc-data` (UC's H2 store), `mlflow-data`,
   `spark-data`. That is far MORE destructive than before, when storage was
   host-installed and out of `-v`'s reach. To start fresh use `./lakehouse reset`
   — it confirms, dry-runs, and resets databases + object store surgically. Plain
   `./lakehouse stop` (no `-v`) is the safe default and preserves all of the above.

6. **Always preflight before start.** Run `./lakehouse preflight` (or `scripts/preflight.sh`) before `./lakehouse start all`. A failing preflight tells you what's wrong before Docker spends 90s composing services that will then fail to connect.

7. **Idempotence assumption.** `lakehouse start <svc>` is safe to re-run; it composes up. `lakehouse stop <svc>` is safe to re-run. If you're unsure of state, run `./lakehouse status --json` and read the JSON (`all_healthy` now includes `connect_grpc_listening`).
