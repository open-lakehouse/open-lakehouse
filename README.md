# open-lakehouse

> A composable OSS lakehouse demo platform — Spark 4.1, Kafka, Airflow, Iceberg, Delta, Unity Catalog OSS, MLflow. Runs locally on Docker. Deploys to AWS. Designed to be set up and torn down by an AI agent.

This repo is the demo-focused sibling of the upstream [lakehouse-stack](https://github.com/lisancao/lakehouse-stack). It strips the platform down to seven OSS services, ships clean AI-skill scaffolding, and uses Unity Catalog OSS as its only catalog. Demos live under `demos/` and start empty — each one follows a fixed README contract so an LLM can run any demo by reading its README.

## Stack

| Layer | Component | Version |
|-------|-----------|---------|
| Compute | Apache Spark | 4.1.0 |
| Streaming | Apache Kafka | 3.6 |
| Orchestration | Apache Airflow | 3.1.6 |
| Open table formats | Apache Iceberg / Delta Lake | 1.10 / 4.0.1 |
| Catalog | Unity Catalog OSS | 0.4.x |
| Experiment tracking | MLflow | 3.1 |
| Object store | SeaweedFS (S3-compatible) | — |
| Metastore | PostgreSQL | 16 |

All components are Apache-2.0 or Apache-compatible permissive licenses. See [NOTICE](NOTICE).

## Quickstart

```bash
git clone https://github.com/open-lakehouse/open-lakehouse
cd open-lakehouse

./lakehouse setup          # validate env, install deps, download ~860MB of JARs
./lakehouse start all      # Spark 4.1 master + worker + Connect server + Kafka
./lakehouse start unity-catalog
./lakehouse start mlflow
./lakehouse status --json  # confirm healthy (incl. Spark Connect gRPC)

# Connect to the cluster from any Python:
#   from pyspark.sql import SparkSession
#   spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
```

## Transport: Connect-first

Default mode is `--spark-connect`. The Spark Connect server runs in container `spark-connect-41` (gRPC on `:15002`). Clients use `SparkSession.builder.remote("sc://localhost:15002")`. Spark Declarative Pipelines (SDP) requires Connect machinery — `pyspark.pipelines` uses it internally.

`--spark-local` (in-process Spark, no Docker) is a forward-compat stub today; the placeholder lives at `demos/local-mode-spark/`. See `docs/architecture.md` for the full transport story.

For the deterministic, branch-on-failure runbook an AI agent uses, see [`.claude/skills/lakehouse-lifecycle/start.md`](.claude/skills/lakehouse-lifecycle/start.md).

## Stop / teardown

```bash
./lakehouse stop all       # safe stop, preserves named volumes
```

Full teardown including data: see [`.claude/skills/lakehouse-lifecycle/stop.md`](.claude/skills/lakehouse-lifecycle/stop.md).

## What's here

```
open-lakehouse/
├── lakehouse                       Top-level CLI (start/stop/status/test/migrate)
├── docker-compose-*.yml            One compose file per service
├── config/                         Spark, Unity Catalog, MLflow, Airflow configs
├── demos/                          Empty placeholders — fill in per the template
├── docs/                           Human-facing documentation
├── scripts/                        Helper scripts (download-jars, testdata, connectivity)
├── tests/                          pytest unit + integration
├── terraform/                      AWS self-hosted deployment
├── terraform-databricks/           Databricks-managed destination
└── .claude/                        AI-assistant skills + agent prompts
    ├── skills/                     Per-domain reference (loaded on demand)
    └── agents/                     Sub-agent system prompts
```

## Demos

The `demos/` directory ships with these four placeholders (Connect-first by default):

- `sdp-medallion/` — Bronze → Silver → Gold via Spark Declarative Pipelines (`spark-pipelines`, Connect-backed)
- `unity-catalog-multi-engine/` — One catalog, multiple engines (Spark Connect + DuckDB)
- `realtime-mode/` — Kafka → Iceberg Structured Streaming over Spark Connect
- `local-mode-spark/` — Placeholder, **not yet implemented**; will back the `--spark-local` flag

Each follows the `demos/_template/` README contract (Purpose / Prereqs / Run / Expected output / Teardown). To scaffold a new demo:

```bash
cp -r demos/_template demos/<your-demo-name>
```

## AI-assistant integration

If you use Claude Code, Cursor, Copilot, or another LLM-driven tool: the project ships with skill files under `.claude/skills/` that the AI loads on demand. The most important is `lakehouse-lifecycle` — a decision-tree-shaped runbook for start, stop, demo, and troubleshooting. See [CLAUDE.md](CLAUDE.md) for the index.

Design principle: CLAUDE.md is a map, skills are the territory, agents are workers. Each lives in its own file with clear discovery metadata; nothing is preloaded into context that isn't needed.

## Deployment

| Target | Path | Notes |
|--------|------|-------|
| Local (Docker) | this repo's compose files | Defaults documented in `docs/deployment/local.md` |
| AWS (self-hosted) | `terraform/` | EC2 + RDS + S3, full self-managed |
| Databricks (managed) | `terraform-databricks/` | Use Delta + UniForm if interop with this OSS catalog is required |

## Why this repo exists

The upstream `lakehouse-stack` repo supports multiple Spark versions, two catalog paths, benchmarks, and several AI-skill iterations. It's reference architecture. **This repo is a demo platform**: a stripped, opinionated subset with strict service surface, clean AI scaffolding, and explicit teardown. It's what we run when we want to show a customer something end-to-end without exposing every degree of freedom.

## Contributing

- Branch from `main`, PR to `main`.
- Pre-commit hooks enforce no-secrets, ShellCheck, Bandit. Install with `pre-commit install`.
- See [SECURITY.md](SECURITY.md) for credential handling rules.
- New demos should ship with a matching template-format README. Use `demos/_template/` as the starting point.

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party attributions.
