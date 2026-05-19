# Demo lifecycle runbook

This document is the human-readable narrative for spinning up the open-lakehouse stack, running a demo, and tearing it down. It mirrors the AI-driven runbook at [`.claude/skills/lakehouse-lifecycle/`](../../.claude/skills/lakehouse-lifecycle/) but with prose instead of decision-tree-shaped checklists.

If you're an LLM agent, prefer the skill files — they're tighter. If you're a human reading this top to bottom, this version is friendlier.

## 0. Prereqs

You need: Docker (Compose v2), Python 3.10+ with Poetry, `psql`, `jq`, `curl`, `nc`, ~20GB free disk. Most macOS / Linux dev machines have these.

```bash
docker version
python --version
poetry --version
```

## 1. First-time setup

Once per machine:

```bash
git clone https://github.com/open-lakehouse/open-lakehouse
cd open-lakehouse

# Copy and edit credentials
cp .env.example .env
# edit .env: set POSTGRES_USER, POSTGRES_PASSWORD, S3_ACCESS_KEY, S3_SECRET_KEY

./lakehouse setup
```

`./lakehouse setup` does a lot:
- Validates `.env` and prompts you to fill placeholders
- Copies `config/spark/spark-defaults.conf.example` → `spark-defaults.conf`
- Downloads JARs (~860MB into `jars/`, idempotent)
- Runs `poetry install`
- Creates the local PostgreSQL database `iceberg_catalog`
- Checks port conflicts and disk space

If anything is red, fix it before continuing. The CLI gives you specific instructions per failure.

## 2. Daily start

```bash
./lakehouse preflight        # verify nothing's blocking us
./lakehouse start all        # Spark 4.1 + Kafka
./lakehouse start unity-catalog
./lakehouse start mlflow
./lakehouse start airflow    # only if demoing orchestration
```

Wait for `lakehouse status --json` to show `"all_healthy": true`. First-ever start takes ~2 minutes (image pulls); subsequent starts are ~30 seconds.

Verify:

```bash
./lakehouse test
```

All six checks should be green: PostgreSQL, SeaweedFS, Kafka, Spark 4.1, Unity Catalog, MLflow/Airflow (if started).

## 3. Run a demo

Demos live under `demos/<name>/`. Each has its own README following the contract documented in [`demos/README.md`](../../demos/README.md). The contract:

1. **Purpose** — one sentence
2. **Prereqs** — services to start
3. **Run** — exact commands with expected stdout
4. **Expected output** — success criteria
5. **Teardown** — exact cleanup commands

To run a demo:

```bash
cat demos/streaming-kafka-to-iceberg/README.md
# follow the Run section, in order
```

The demos that ship in the initial commit are placeholders. Pick one, scaffold from `demos/_template/`, build it out.

## 4. Stop

For a normal stop (preserves all data):

```bash
./lakehouse stop all
./lakehouse stop unity-catalog
./lakehouse stop mlflow
./lakehouse stop airflow
```

Containers go away. Named volumes (UC metadata, MLflow runs, Airflow DAG history) persist. Restart later from step 2 and your state is back.

For a full teardown (destructive — accept data loss):

```bash
docker compose -f docker-compose-spark41.yml       down -v
docker compose -f docker-compose-kafka.yml         down -v
docker compose -f docker-compose-unity-catalog.yml down -v
docker compose -f docker-compose-airflow.yml       down -v
docker compose -f docker-compose-mlflow.yml        down -v
```

This wipes Unity Catalog metadata, MLflow tracking history, and Airflow state. Use when you want to start completely fresh.

## 5. When something goes wrong

```bash
./lakehouse status --json    # which services aren't healthy
docker ps -a                  # any crash-looping containers
./lakehouse logs <service>    # tail logs interactively
```

For a symptom-to-fix table, see [`.claude/skills/lakehouse-lifecycle/troubleshoot.md`](../../.claude/skills/lakehouse-lifecycle/troubleshoot.md).

## 6. AWS deployment

For self-hosted AWS deployment (EC2 + RDS + S3), see [`docs/deployment/aws.md`](../deployment/aws.md) and the `terraform/` directory. The same `lakehouse` CLI works against remote infrastructure once the environment variables in `.env` point at the AWS endpoints instead of localhost.
