#!/usr/bin/env bash
# Teardown script for <demo-name>.
# Removes every artifact this demo created. Safe to re-run.

set -euo pipefail

DEMO_NAME="<demo-name>"
echo "-> teardown: ${DEMO_NAME}"

# Drop Iceberg tables (idempotent)
# docker exec spark-master-41 /opt/spark/bin/spark-sql -e "DROP TABLE IF EXISTS iceberg.<schema>.<table>;"

# Delete Kafka topics (idempotent)
# docker exec kafka kafka-topics --delete --if-exists --topic <topic> --bootstrap-server localhost:9092

# Clear MLflow runs by experiment (commented; requires MLflow CLI)
# mlflow experiments delete --experiment-id <id>

# Stop demo-specific services (commented; uncomment if this demo started them)
# ./lakehouse stop mlflow

echo "ok teardown: ${DEMO_NAME} complete"
