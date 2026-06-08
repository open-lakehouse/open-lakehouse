# open-lakehouse

> A composable OSS lakehouse demo platform — Spark 4.1 (Connect-first), Kafka, Airflow, Iceberg, Delta, Unity Catalog OSS, MLflow. Runs locally on Docker. Deploys to AWS. Designed to be set up and torn down by an AI agent.

This repo is the demo-focused sibling of the upstream [lakehouse-stack](https://github.com/lisancao/lakehouse-stack). It strips the platform down to seven OSS services, ships clean AI-skill scaffolding, and uses Unity Catalog OSS as its only catalog. Demos live under `demos/` and start empty — each one follows a fixed README contract so an LLM can run any demo by reading its README.

## Stack

| Layer | Component | Version |
|-------|-----------|---------|
| Compute | Apache Spark | 4.1.0 |
| Client transport | **Spark Connect** (gRPC, port 15002) | bundled with Spark 4.1 |
| Streaming | Apache Kafka | 3.6 |
| Orchestration | Apache Airflow | 3.1.6 |
| Open table formats | Apache Iceberg / Delta Lake | 1.10 / 4.2.0 |
| Catalog | Unity Catalog OSS | 0.4.x |
| Experiment tracking | MLflow | 3.12 |
| Object store | SeaweedFS (S3-compatible) | — |
| Metastore | PostgreSQL | 16 |

All components are Apache-2.0 or Apache-compatible permissive licenses. See [NOTICE](NOTICE).

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                                 │
│  PySpark (sc://...)  ·  spark-pipelines (SDP)  ·  DuckDB  ·  PyIceberg   │
└────────┬──────────────────────────────────────────────────┬──────────────┘
         │ Spark Connect gRPC                               │ Iceberg REST
         │ sc://localhost:15002                             │ (multi-engine)
         ▼                                                  │
┌─────────────────────────────────────┐                     │
│  COMPUTE                            │                     │
│   spark-connect-41   :15002         │                     │
│   spark-master-41    :7078  UI 8082 │                     │
│   spark-worker-41           UI 8083 │                     │
└──────────┬──────────────────────────┘                     │
           │ Iceberg REST                                   │
           ▼                                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  CATALOG                                                             │
│   Unity Catalog OSS :8081  ──  PostgreSQL :5432 (UC metastore)       │
└──────────┬───────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STORAGE                                                             │
│   SeaweedFS :8333  →  s3://warehouse/{bronze,silver,gold}/           │
└──────────────────────────────────────────────────────────────────────┘

      Kafka :9092 / Zookeeper :2181  feed events into the Connect client,
      which lands them in Iceberg via Unity Catalog.
```

Optional services not shown: MLflow Tracking + AI Gateway (`:5000`/`:5001`), Airflow (`:8085`), JupyterLab (`:8889`). Full details in [`docs/architecture.md`](docs/architecture.md).

## Quickstart

```bash
git clone https://github.com/open-lakehouse/open-lakehouse
cd open-lakehouse

cp .env.example .env       # fill in POSTGRES_*, S3_* placeholders
./lakehouse setup          # validate env, install deps, download ~860MB of JARs
./lakehouse start all      # Spark 4.1 master + worker + Connect server + Kafka
./lakehouse start unity-catalog
./lakehouse start mlflow
./lakehouse status --json  # confirm healthy (incl. spark.connect_grpc_listening)
```

Connect from any Python:

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
spark.sql("SHOW CATALOGS").show()
```

Or read `LAKEHOUSE_SPARK_REMOTE` from the env exported by `./lakehouse` instead of hardcoding.

For the deterministic, branch-on-failure runbook an AI agent uses, see [`.claude/skills/lakehouse-lifecycle/start.md`](.claude/skills/lakehouse-lifecycle/start.md).

## Transport: Connect-first

Default CLI mode is `--spark-connect`. The Spark Connect server runs in container `spark-connect-41` (gRPC on `:15002`). Clients use `SparkSession.builder.remote("sc://localhost:15002")`.

Spark Declarative Pipelines (SDP) **requires** Connect machinery — `pyspark.pipelines` uses `SparkConnectGraphElementRegistry` internally even though `spark-pipelines run` doesn't open `sc://` explicitly. Don't disable the Connect server.

`--spark-local` (in-process Spark, no Docker) is a forward-compat stub today; the placeholder lives at [`demos/local-mode-spark/`](demos/local-mode-spark/). See [`docs/architecture.md`](docs/architecture.md) for the full transport story.

## Stop / teardown

```bash
./lakehouse stop all       # safe stop, preserves named volumes
```

Full teardown including data: see [`.claude/skills/lakehouse-lifecycle/stop.md`](.claude/skills/lakehouse-lifecycle/stop.md).

## What's here

```
open-lakehouse/
├── lakehouse                       Top-level CLI (start/stop/status/test/migrate)
├── docker-compose-*.yml            One compose file per service (Spark + Connect, Kafka, UC, MLflow, Airflow, Notebooks)
├── config/                         Spark, Unity Catalog, MLflow, Airflow configs (examples only — live configs are gitignored)
├── demos/                          Four demo slots (see below)
├── docs/                           Human-facing documentation
├── scripts/                        Helper scripts (download-jars, testdata, connectivity smoke tests)
├── tests/                          pytest unit + integration
├── terraform/                      AWS self-hosted deployment (EMR + RDS + S3 + UC)
├── terraform-databricks/           Databricks-managed destination
└── .claude/                        AI-assistant skills + agent prompts
    ├── skills/                     Per-domain reference (loaded on demand)
    └── agents/                     Sub-agent system prompts
```

## Demos

The `demos/` directory ships with these four placeholders (Connect-first by default):

| Demo | Transport | What it shows |
|------|-----------|----------------|
| [`sdp-medallion/`](demos/sdp-medallion/) | `spark-pipelines` (Connect-backed) | Bronze → Silver → Gold via Spark Declarative Pipelines |
| [`unity-catalog-multi-engine/`](demos/unity-catalog-multi-engine/) | Spark Connect + DuckDB | One catalog, multiple engines reading the same Iceberg table |
| [`realtime-mode/`](demos/realtime-mode/) | Spark Connect (Structured Streaming) | Kafka → Iceberg with watermarked dedup |
| [`local-mode-spark/`](demos/local-mode-spark/) | Local (no cluster) — **not yet implemented** | In-process SparkSession; placeholder for `--spark-local` |

Each follows the [`demos/_template/`](demos/_template/) README contract (Purpose / Prereqs / Run / Expected output / Teardown). To scaffold a new demo:

```bash
cp -r demos/_template demos/<your-demo-name>
```

## AI-assistant integration

If you use Claude Code, Cursor, Copilot, or another LLM-driven tool: the project ships with skill files under [`.claude/skills/`](.claude/skills/) that the AI loads on demand. The most important is `lakehouse-lifecycle` — a decision-tree-shaped runbook for start, stop, demo, and troubleshooting. See [CLAUDE.md](CLAUDE.md) for the index.

Design principle: CLAUDE.md is a map, skills are the territory, agents are workers. Each lives in its own file with clear discovery metadata; nothing is preloaded into context that isn't needed.

## Deployment

| Target | Path | Notes |
|--------|------|-------|
| Local (Docker) | this repo's compose files | Defaults documented in [`docs/deployment/local.md`](docs/deployment/local.md) |
| AWS (self-hosted) | [`terraform/`](terraform/) | EMR + RDS + S3 + Unity Catalog (no JDBC catalog path) |
| Databricks (managed) | [`terraform-databricks/`](terraform-databricks/) | Use Delta + UniForm if interop with managed UC is required |

## Security

- **Live credentials are gitignored** (`.env`, `config/spark/spark-defaults.conf`, `config/unity-catalog/server.properties`, all `*.tfvars` except `.example`, all PEM/JKS/keystore files).
- **Pre-commit hooks** enforce: `detect-secrets`, `detect-private-key`, Bandit (Python), ShellCheck (shell). Install with `pre-commit install`.
- See [SECURITY.md](SECURITY.md) for full credential-handling rules.

## Why this repo exists

The upstream `lakehouse-stack` repo supports multiple Spark versions, two catalog paths, benchmarks, and several AI-skill iterations. It's reference architecture. **This repo is a demo platform**: a stripped, opinionated subset with strict service surface, Connect-first transport, clean AI scaffolding, and explicit teardown. It's what we run when we want to show a customer something end-to-end without exposing every degree of freedom.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — has separate sections for humans and for AI agents (the conventions for `.claude/skills/`, the demo contract, and what not to fabricate are non-obvious enough to deserve their own write-up).

Community standards: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party attributions.
