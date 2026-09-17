#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""MLflow experiment tracking + model registry (Spark Connect + MLflow).

Ported from the containerized-lakehouse `05_MLflow_Tracking` notebook and reworked
for the open-lakehouse stack. Data is sourced and feature-prepared in Spark
Connect, then pulled to the client (`toPandas`) and trained with scikit-learn.

Why sklearn and not Spark ML: `mlflow.spark.log_model` saves the model via Spark
writes, which use the S3A rename committer — and SeaweedFS does not support it
(same failure as a raw `parquet` write). `mlflow.sklearn.log_model` uploads the
artifact through boto3, which SeaweedFS handles, so the tracking + registry flow
works end to end. (Spark ML itself does run over Connect; only the sparkml
artifact save is blocked.)

Shows: experiment tracking (params/metrics/model per run), run comparison, Model
Registry registration, a `champion` alias, and loading the champion for scoring.

Run:
    poetry run python demos/mlflow-tracking/mlflow_tracking.py
"""

from __future__ import annotations

import os
import random

import pandas as pd
from pyspark.sql import SparkSession

# mlflow + scikit-learn are demo-only client deps (documented `poetry run pip install
# mlflow scikit-learn`, not in the core pyproject). Fail with a clear hint, not a raw
# ModuleNotFoundError, if they are missing — this demo cannot run without them.
try:
    import mlflow
    import mlflow.sklearn
    from mlflow.tracking import MlflowClient
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"mlflow-tracking needs a demo dependency that isn't installed ('{exc.name}').\n"
        "  Install it:  poetry run pip install mlflow scikit-learn"
    ) from exc

REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
EXPERIMENT = "lakehouse-revenue-prediction"
MODEL_NAME = "lakehouse-revenue-predictor"

# MLflow client needs the tracking server and the S3 artifact store (SeaweedFS).
os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:8333")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "lakehouse_s3")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "lakehouse_s3_secret")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

PRODUCTS = ["Laptop", "Phone", "Tablet", "Headphones", "Monitor", "Keyboard", "Mouse"]
REGIONS = ["North America", "Europe", "Asia", "South America"]


def source_features(spark: SparkSession) -> pd.DataFrame:
    """Generate + feature-select sales in Spark Connect, return a pandas frame.

    Amount is loosely driven by a product base price and quantity (plus noise) so
    the models have real signal to fit and can be meaningfully ranked.
    """
    random.seed(42)
    base = {p: 100 + 120 * i for i, p in enumerate(PRODUCTS)}
    rows = []
    for _ in range(3000):
        product = random.choice(PRODUCTS)
        region = random.choice(REGIONS)
        quantity = random.randint(1, 10)
        amount = round(base[product] * quantity * random.uniform(0.85, 1.15), 2)
        rows.append((product, region, quantity, amount))
    spark.createDataFrame(
        rows, ["product", "region", "quantity", "amount"]
    ).createOrReplaceTempView("sales")
    # Feature selection in Spark, then pull the (small) frame to the client.
    pdf = spark.sql("SELECT product, region, quantity, amount FROM sales").toPandas()
    print(f"[0] Sourced {len(pdf):,} rows from Spark Connect")
    return pdf


def prepare(pdf: pd.DataFrame):
    """One-hot encode categoricals; split into train/test."""
    x = pd.get_dummies(
        pdf[["product", "region", "quantity"]], columns=["product", "region"]
    )
    y = pdf["amount"]
    return train_test_split(x, y, test_size=0.2, random_state=42)


def log_run(name: str, model, x_tr, x_te, y_tr, y_te, params: dict) -> dict:
    """Fit, evaluate, and log one run; return this run's id + metrics for ranking."""
    with mlflow.start_run(run_name=name) as run:
        model.fit(x_tr, y_tr)
        pred = model.predict(x_te)
        rmse = mean_squared_error(y_te, pred) ** 0.5
        r2 = r2_score(y_te, pred)
        mlflow.log_params(params)
        mlflow.log_metrics({"rmse": rmse, "r2": r2})
        # MLflow 3 logs a first-class "logged model" with URI models:/m-<id>; return
        # that so step 3 registers it directly. Registering runs:/<id>/model would hit
        # the "no artifacts at 'model', using models:/m-… instead" fallback, because
        # under MLflow 3 the model is not stored at the run-relative path.
        info = mlflow.sklearn.log_model(model, name="model")
        print(f"    {name:22} RMSE={rmse:9.2f}  R2={r2:.4f}")
        return {
            "name": name,
            "run_id": run.info.run_id,
            "model_uri": info.model_uri,
            "rmse": rmse,
            "r2": r2,
            "model_type": params.get("model_type", name),
        }


def main() -> None:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    print(f"MLflow tracking URI: {mlflow.get_tracking_uri()}")

    x_tr, x_te, y_tr, y_te = prepare(source_features(spark))
    spark.stop()  # training is client-side sklearn from here on

    # --- 1. Experiment tracking (three runs) --------------------------------
    # Re-run safety: teardown soft-deletes the experiment; restore it so
    # set_experiment does not fail on a trashed name.
    client = MlflowClient()
    existing = client.get_experiment_by_name(EXPERIMENT)
    if existing is not None and existing.lifecycle_stage == "deleted":
        client.restore_experiment(existing.experiment_id)
    mlflow.set_experiment(EXPERIMENT)
    print("[1] Training runs:")
    results = [
        log_run(
            "linear-regression",
            LinearRegression(),
            x_tr,
            x_te,
            y_tr,
            y_te,
            {"model_type": "LinearRegression"},
        ),
        log_run(
            "random-forest",
            RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42),
            x_tr,
            x_te,
            y_tr,
            y_te,
            {"model_type": "RandomForest", "n_estimators": 50, "max_depth": 8},
        ),
        log_run(
            "random-forest-tuned",
            RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42),
            x_tr,
            x_te,
            y_tr,
            y_te,
            {"model_type": "RandomForest", "n_estimators": 100, "max_depth": 12},
        ),
    ]

    # --- 2. Compare runs (this invocation only, so leftover runs from a prior,
    #        non-torn-down experiment cannot affect champion selection) -------
    ranked = sorted(results, key=lambda r: r["rmse"])
    print("\n[2] This run's models by RMSE (best first):")
    for r in ranked:
        print(f"    {r['name']:22} RMSE={r['rmse']:9.2f}  R2={r['r2']:.4f}")

    # --- 3. Model registry: register the best, promote to champion ----------
    best = ranked[0]
    mv = mlflow.register_model(best["model_uri"], MODEL_NAME)
    client.update_registered_model(
        MODEL_NAME,
        description="Predicts transaction amount from product, region, quantity.",
    )
    client.set_registered_model_alias(MODEL_NAME, "champion", mv.version)
    print(
        f"\n[3] Registered '{MODEL_NAME}' v{mv.version} "
        f"({best['model_type']}, RMSE={best['rmse']:.2f}) -> alias 'champion'"
    )

    # --- 4. Load the champion from the registry and score -------------------
    champion = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@champion")
    preds = champion.predict(x_te.head(5))
    print("[4] Champion predictions (first 5):", [round(float(p), 2) for p in preds])

    print("\nmlflow-tracking demo complete.")


if __name__ == "__main__":
    main()
