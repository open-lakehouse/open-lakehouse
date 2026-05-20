#!/usr/bin/env bash
# Teardown for sdp-imperative-to-declarative. Safe to re-run.
set -euo pipefail

echo "→ teardown: sdp-imperative-to-declarative"

docker exec spark-master-41 /opt/spark/bin/spark-sql --silent <<'SQL' 2>/dev/null || true
DROP TABLE IF EXISTS spark_catalog.default.imp_orders_bronze;
DROP TABLE IF EXISTS spark_catalog.default.imp_orders_silver;
DROP TABLE IF EXISTS spark_catalog.default.imp_orders_gold;
DROP TABLE IF EXISTS spark_catalog.default.dec_orders_bronze;
DROP TABLE IF EXISTS spark_catalog.default.dec_orders_silver;
DROP TABLE IF EXISTS spark_catalog.default.dec_orders_gold;
SQL

docker exec spark-master-41 rm -rf /tmp/declarative-medallion-storage /tmp/declarative 2>/dev/null || true
docker start spark-connect-41 >/dev/null 2>&1 || true

echo "✓ teardown: sdp-imperative-to-declarative complete"
