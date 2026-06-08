# CLAUDE.md — open-lakehouse

You are helping with **open-lakehouse**, a composable OSS lakehouse demo platform. This file is the always-loaded map. The territory (deep references) lives in `.claude/skills/`. Workers (delegated sub-agents) live in `.claude/agents/`.

## Stack

Spark 4.1 (Connect-first) · Kafka 3.6 · Airflow 3.1 · Delta 4.2 + Iceberg 1.10 (both extensions enabled) · Unity Catalog OSS 0.4.x · MLflow 3.1 · SeaweedFS (S3) · PostgreSQL.

Catalogs (verified — see `.claude/skills/unity-catalog-oss/`):
- `unity.<schema>.<table>` — Unity Catalog OSS via its Spark connector. **Delta only. Primary write path.**
- `iceberg.<schema>.<table>` — UC OSS Iceberg REST endpoint. **Read-only** — UC OSS 0.4.x exposes no Iceberg write endpoints.
- `spark_catalog.<schema>.<table>` — default catalog set to `DeltaCatalog`; path-based / local Delta.

Runs locally via Docker Compose; deploys to AWS via `terraform/`. Optional Databricks-managed destination in `terraform-databricks/`.

## Golden rules (read every session)

1. **Catalog is Unity Catalog OSS only.** No PostgreSQL JDBC catalog path exists. If you see `spark.sql.catalog.iceberg.type=jdbc` or `.jdbc.user`/`.jdbc.password`, that's a bug — fix the config, don't work around the symptom.
2. **Spark is 4.1 only.** No `--version` flag. Compose file is `docker-compose-spark41.yml`. Master container is `spark-master-41`.
3. **Connect-first transport.** Default CLI mode is `--spark-connect`. Spark Connect server runs in `spark-connect-41` on port 15002. Clients use `SparkSession.builder.remote("sc://localhost:15002")` or read `LAKEHOUSE_SPARK_REMOTE`. SDP requires Connect (pyspark.pipelines uses it internally). `--spark-local` is a stub — exits with "not yet implemented."
4. **Don't `docker compose down -v` without explicit user consent.** `-v` wipes named volumes (UC metadata, MLflow runs, Airflow history). `./lakehouse stop` is safe and is what you should default to.
5. **Demo slots.** Four: `sdp-medallion` (**built** — SDP→UC→Delta medallion), `unity-catalog-multi-engine`, `realtime-mode` (placeholders), `local-mode-spark` (deferred). Each follows the `demos/_template/` contract. Don't fabricate placeholder demos — scaffold from the template when asked.
6. **AGENTS.md is a pointer**, not a duplicate of this file. Keep CLAUDE.md authoritative.
7. **Always work on a feature branch.** Never commit directly to `main`. Create a dedicated branch (e.g. `feat/<short-description>`) before the first file change. See [.agents/rules/branching-rule.mdc](.agents/rules/branching-rule.mdc) for the full workflow and naming conventions.

## File index — where to look for what

| You want… | Read |
|-----------|------|
| Start / stop / smoke the stack | `.claude/skills/lakehouse-lifecycle/` |
| Spark 4.1 PySpark / SQL reference | `.claude/skills/spark-4-1/` |
| Spark Declarative Pipelines (canonical) | `.claude/skills/sdp/` |
| Iceberg ops (compaction, snapshots, time travel) | `.claude/skills/iceberg-ops/` |
| Delta ops (OPTIMIZE, VACUUM, UniForm) | `.claude/skills/delta-ops/` |
| Unity Catalog OSS REST API + multi-engine | `.claude/skills/unity-catalog-oss/` |
| Kafka + Structured Streaming | `.claude/skills/kafka-streaming/` |
| Airflow 3.1 DAGs and 2→3 gotchas | `.claude/skills/airflow-3/` |
| MLflow tracking + AI Gateway | `.claude/skills/mlflow/` |
| Cross-service work (delegated agent) | `.claude/agents/lakehouse-engineer.md` |
| Human-facing setup | `README.md`, `docs/getting-started/` |
| Demo-lifecycle narrative for humans | `docs/runbooks/demo-lifecycle.md` |

## CLI cheat sheet

```bash
./lakehouse setup                   # validate env, install deps, download JARs
./lakehouse start all               # Spark 4.1 master + worker + Connect + Kafka
./lakehouse start unity-catalog     # UC OSS REST server
./lakehouse start mlflow            # MLflow tracking + AI Gateway
./lakehouse start airflow           # Airflow scheduler + UI
./lakehouse status --json           # machine-readable health (incl. connect_grpc_listening)
./lakehouse test                    # connectivity tests, returns exit code
./lakehouse stop all                # safe stop (volumes preserved)

# Spark transport flags
./lakehouse --spark-connect start   # explicit Connect mode (same as default)
./lakehouse --spark-local <cmd>     # exits — not yet implemented
```

For the full deterministic runbook, see `.claude/skills/lakehouse-lifecycle/start.md`.

## Version pins (do not change without testing)

- Spark 4.1.0 (Scala 2.13, Java 21)
- Iceberg 1.10.0
- Delta 4.2.0 (4.0.x breaks on Spark 4.1 — ABI mismatch)
- Airflow 3.1.6
- Unity Catalog OSS 0.4.1 (`newfrontdocker/unitycatalog:v0.4.1`)
- Unity Catalog Spark connector 0.3.0
- MLflow 3.1
- AWS SDK v2 2.24.6 (exact, for Hadoop 3.4.1 compatibility)

## Ports

| Service | Port |
|---------|------|
| PostgreSQL | 5432 |
| SeaweedFS (S3) | 8333 |
| Spark master | 7078 (UI 8082) |
| Spark Connect (gRPC) | 15002 |
| Kafka | 9092 |
| Zookeeper | 2181 |
| Unity Catalog | 8081 |
| Airflow | 8085 |
| MLflow Tracking | 5000 |
| MLflow AI Gateway | 5001 |

## Code style

- Python 3.10+; Black (88 cols), Ruff.
- PySpark imports: `from pyspark.sql import functions as f`. Never `import *`.
- Shell: ShellCheck-clean.
- No emoji in code unless asked.

## Security

- **Never commit credentials.** `.env` is gitignored. See `SECURITY.md`.
- Pre-commit hooks enforce: detect-secrets, no private keys, Bandit (Python), ShellCheck (shell).
- All bundled OSS components are Apache-2.0 compatible. See `NOTICE`.

## For AI agents

The skills under `.claude/skills/` are reference material loaded on demand. Each has YAML frontmatter with a `description:` — match the user's task against descriptions and load only what's relevant. Don't preload everything.

The `lakehouse-lifecycle` skill is decision-tree shaped: each sub-file is a deterministic checklist. An LLM should be able to execute `start.md` top-to-bottom against a clean machine and reach a healthy stack.

When delegating to a sub-agent (Task tool), use `subagent_type=general-purpose` and reference `.claude/agents/lakehouse-engineer.md` for context on cross-service work.
