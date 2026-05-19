---
name: mlflow
description: MLflow 3.1 (tracking + AI Gateway) on this stack. Load when logging experiments from Spark/Python jobs, registering models, or wiring AI Gateway routes to Anthropic / Ollama for LLM-in-pipeline patterns.
---

# MLflow 3.1

Tracking server: `http://localhost:5000`. AI Gateway: `http://localhost:5001`. Both in `docker-compose-mlflow.yml`. Backend: PostgreSQL (`mlflow` database). Artifact store: SeaweedFS (`s3://mlflow/`).

## Tracking client

```python
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("my-experiment")

with mlflow.start_run() as run:
    mlflow.log_param("lr", 0.01)
    mlflow.log_metric("accuracy", 0.94)
    mlflow.log_artifact("plot.png")
    print(run.info.run_id)
```

Set `MLFLOW_TRACKING_URI=http://localhost:5000` in `.env` and clients pick it up without explicit `set_tracking_uri`.

## Spark autologging

```python
import mlflow.spark
mlflow.spark.autolog()    # logs Spark ML pipelines, datasets, params

# or specifically for sklearn-style estimators
import mlflow.sklearn
mlflow.sklearn.autolog()
```

Autolog requires the run to be active (`with mlflow.start_run():`).

## Model registry

```python
mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name="orders-classifier",
)
```

Stage transitions (Staging → Production) are managed via the UI or `mlflow.MlflowClient().transition_model_version_stage(...)`.

## AI Gateway (port 5001)

The Gateway is an LLM proxy with route-based config in `config/mlflow/gateway-config.yml`. Pre-configured routes (verify the file in this repo, but typically):

- `chat-anthropic` — Anthropic Claude (requires `ANTHROPIC_API_KEY` in `.env`)
- `chat-ollama` — local Ollama models (requires Ollama running on the host)

Call from Python:

```python
from mlflow.deployments import get_deploy_client
client = get_deploy_client("http://localhost:5001")

response = client.predict(
    endpoint="chat-anthropic",
    inputs={"messages": [{"role": "user", "content": "Summarize this Iceberg snapshot."}]},
)
```

Use cases on this stack:

- LLM-as-evaluator inside a Spark UDF
- Generating documentation strings for new tables in a Iceberg maintenance DAG
- Routing demo queries to a local Ollama model to avoid API costs

## Common pitfalls

- **`Connection refused: localhost:5000`** — MLflow container isn't up. `./lakehouse start mlflow`.
- **`Artifact upload failed: S3 access denied`** — Mlflow's S3 creds (in `docker-compose-mlflow.yml` env) don't match the SeaweedFS keys in `.env`. They must match.
- **Autolog logs to the wrong tracking server** — `MLFLOW_TRACKING_URI` env var beats `set_tracking_uri()` call order. Set the env var explicitly.
- **Spark autologging duplicate runs** — `mlflow.spark.autolog()` + manual `start_run()` can create nested runs. Choose one.

## Performance / cleanup

MLflow artifacts in SeaweedFS accumulate quickly. Cleanup:

```bash
# Delete runs older than 30 days via MLflow API
mlflow gc --backend-store-uri postgresql://... --older-than 30
```

For demos, just `docker compose -f docker-compose-mlflow.yml down -v` to wipe everything.
