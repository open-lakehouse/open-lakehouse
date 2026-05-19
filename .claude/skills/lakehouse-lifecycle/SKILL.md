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

3. **Never `docker compose down -v` without confirming.** The `-v` flag wipes named volumes (PostgreSQL → loses Unity Catalog state; SeaweedFS → loses all object data). Plain `down` is safe and is what `lakehouse stop` uses.

4. **Always preflight before start.** Run `./lakehouse preflight` (or `scripts/preflight.sh`) before `./lakehouse start all`. A failing preflight tells you what's wrong before Docker spends 90s composing services that will then fail to connect.

5. **Idempotence assumption.** `lakehouse start <svc>` is safe to re-run; it composes up. `lakehouse stop <svc>` is safe to re-run. If you're unsure of state, run `./lakehouse status --json` and read the JSON.
