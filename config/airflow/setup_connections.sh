#!/bin/bash
# Setup Airflow connections for open-lakehouse.
# Run this after the Airflow container is initialized.

set -e

echo "Setting up Airflow connections..."

# Kafka
airflow connections delete kafka_default 2>/dev/null || true
airflow connections add kafka_default \
    --conn-type kafka \
    --conn-extra '{"bootstrap.servers": "localhost:9092", "group.id": "airflow-consumer", "security.protocol": "PLAINTEXT"}'
echo "✓ Kafka connection configured"

# Spark 4.1 (the only Spark in this repo)
airflow connections delete spark_local 2>/dev/null || true
airflow connections add spark_local \
    --conn-type spark \
    --conn-host "spark://localhost" \
    --conn-port 7078 \
    --conn-extra '{"deploy_mode": "client", "spark_home": "/opt/spark"}'
echo "✓ Spark 4.1 connection configured (spark_local)"

# PostgreSQL — system PostgreSQL hosting the Unity Catalog metastore
airflow connections delete postgres_default 2>/dev/null || true
airflow connections add postgres_default \
    --conn-type postgres \
    --conn-host localhost \
    --conn-port 5432 \
    --conn-login "${POSTGRES_USER:-postgres}" \
    --conn-password "${POSTGRES_PASSWORD:-}" \
    --conn-schema postgres
echo "✓ PostgreSQL connection configured (postgres_default)"

# Unity Catalog REST endpoint as an HTTP connection
airflow connections delete unity_catalog 2>/dev/null || true
airflow connections add unity_catalog \
    --conn-type http \
    --conn-host localhost \
    --conn-port 8081 \
    --conn-schema http
echo "✓ Unity Catalog connection configured (unity_catalog)"

# MLflow tracking URI as an HTTP connection
airflow connections delete mlflow 2>/dev/null || true
airflow connections add mlflow \
    --conn-type http \
    --conn-host localhost \
    --conn-port 5000 \
    --conn-schema http
echo "✓ MLflow connection configured (mlflow)"

# Default Airflow variables
airflow variables set spark_version "4.1"
airflow variables set kafka_bootstrap_servers "localhost:9092"
airflow variables set uc_endpoint "http://localhost:8081/api/2.1/unity-catalog/iceberg"
echo "✓ Variables configured"

echo ""
echo "Airflow connections setup complete."
echo "Access Airflow UI at: http://localhost:8085"
