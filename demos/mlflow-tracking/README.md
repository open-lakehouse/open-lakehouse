# MLflow experiment tracking + model registry

> Track competing models, compare runs, register the best, and load it back by a `champion` alias — MLflow on the open-lakehouse stack.

## Purpose

The classic MLflow workflow: log three competing models as tracked runs (params, metrics, model
artifact), compare them, register the winner in the Model Registry, promote it with a `champion`
alias, and load the champion back for scoring. Data is sourced and feature-prepared in Spark
Connect, then trained client-side with scikit-learn.

(Distinct from `demos/mlflow/`, which is a conversational-analytics agent that uses MLflow for
evaluation — this demo is about experiment tracking and the model registry.)

## Prereqs

- Spark 4.1 + Connect + storage: `./lakehouse start all`
- MLflow tracking server: `./lakehouse start mlflow` (UI at `http://localhost:5000`)
- Python client deps: `poetry install`, plus `poetry run pip install mlflow scikit-learn`.

The MLflow client reaches the S3 artifact store (SeaweedFS) directly; the demo sets sensible
defaults (`MLFLOW_S3_ENDPOINT_URL`, `AWS_*`), overridable via the environment. Tracking URI is
`MLFLOW_TRACKING_URI` (default `http://localhost:5000`).

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

## Run

```bash
poetry run python demos/mlflow-tracking/mlflow_tracking.py
```

Expected stdout snippets, in order:

```
[0] Sourced 3,000 rows from Spark Connect
[1] Training runs:
    linear-regression      RMSE=   795.44  R2=0.8446
    random-forest          RMSE=   301.12  R2=0.9777
    random-forest-tuned    RMSE=   300.72  R2=0.9778
```

```
[2] This run's models by RMSE (best first):
    random-forest-tuned    RMSE=   300.72  R2=0.9778
```

```
[3] Registered 'lakehouse-revenue-predictor' v<N> (RandomForest, RMSE=300.72) -> alias 'champion'
[4] Champion predictions (first 5): [918.21, 2318.98, ...]
```

## Expected output

- An MLflow experiment `lakehouse-revenue-prediction` with three runs, visible at
  `http://localhost:5000`. Metrics are deterministic (`random_state=42`): RandomForest
  (R²≈0.978) clearly beats LinearRegression (R²≈0.845).
- A registered model `lakehouse-revenue-predictor` promoted to a `champion` alias. The version is
  `1` on a clean run and **increments on each re-run** (registering adds a version) — the success
  signal is the `champion` alias resolving, not a specific version number; run the teardown first
  if you want a clean `v1`.
- Champion selection ranks **only this invocation's three runs**, so leftover runs from an earlier
  (non-torn-down) experiment do not affect which model becomes champion.
- The champion loads from `models:/lakehouse-revenue-predictor@champion` and scores test rows.

### Why sklearn, not Spark ML

Spark ML runs over Connect, but `mlflow.spark.log_model` saves the model via Spark writes, which
use the S3A rename committer — and SeaweedFS does not support it (`Could not rename ..._temporary`).
`mlflow.sklearn.log_model` uploads the artifact through boto3, which SeaweedFS handles, so the
tracking + registry flow completes. Spark Connect still does the data sourcing and feature prep.

## Teardown

```bash
bash demos/mlflow-tracking/teardown.sh
```
