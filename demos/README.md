# Demos

This directory holds runnable end-to-end demonstrations. Each demo lives in its own subdirectory and follows the contract in [`_template/README.md`](_template/README.md). An AI agent that knows the contract can run any demo by reading the demo's README — no per-demo scripting needed.

## Demo contract

Every `demos/<name>/README.md` has these five sections, in order, with these names:

1. **Purpose** — one sentence describing what this demo shows.
2. **Prereqs** — which services must be running (Spark, Kafka, UC, MLflow, Airflow) and any data prep.
3. **Run** — exact commands in order, each annotated with the expected stdout snippet.
4. **Expected output** — what success looks like (tables created, metrics logged, DAG run id).
5. **Teardown** — exact commands to remove all demo artifacts, or `bash teardown.sh`.

Demos that ship with a `teardown.sh` use the standard shape:

```bash
#!/usr/bin/env bash
set -euo pipefail
# Drop tables, delete topics, clear MLflow runs, etc.
```

## Empty placeholders shipped with this repo

| Demo | What it will show |
|------|-------------------|
| `streaming-kafka-to-iceberg/` | Structured Streaming from Kafka into an Iceberg bronze table. |
| `sdp-medallion/` | Bronze → Silver → Gold built declaratively with Spark Declarative Pipelines. |
| `delta-vs-iceberg/` | Same workload on both formats — compare query plans, file layouts, time travel. |
| `unity-catalog-multi-engine/` | One catalog, multiple engines (Spark + DuckDB + PyIceberg) reading the same table. |
| `mlflow-tracking/` | Spark ML training run logged to MLflow + AI Gateway-mediated LLM evaluation. |
| `airflow-orchestration/` | Airflow 3.1 DAG that runs an SDP pipeline + Iceberg maintenance + MLflow log. |

Each is a `.gitkeep` placeholder. Build them out one by one — don't fabricate content. To scaffold a new demo (or fill a placeholder), copy the template:

```bash
cp -r demos/_template demos/<name>
# then edit demos/<name>/README.md
```

## How an LLM uses this

1. User says "run the streaming-kafka-to-iceberg demo."
2. Agent reads `.claude/skills/lakehouse-lifecycle/demo.md` to recall the contract.
3. Agent reads `demos/streaming-kafka-to-iceberg/README.md`.
4. Agent checks "Prereqs" against `./lakehouse status --json`.
5. Agent runs commands from "Run" in order, comparing stdout to "Expected output".
6. After user confirms success (or on error), agent runs "Teardown".

No demo-specific skill files. The lifecycle skill + the demo's README are enough.
