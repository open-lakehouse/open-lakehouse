#!/usr/bin/env bash
# Teardown for sdp-streaming-batch-sql. Safe to re-run.
set -euo pipefail

echo "→ teardown: sdp-streaming-batch-sql"

docker exec spark-master-41 /opt/spark/bin/spark-sql --silent <<'SQL' 2>/dev/null || true
DROP TABLE IF EXISTS spark_catalog.default.sxb_rollup;
DROP TABLE IF EXISTS spark_catalog.default.sxb_clean;
DROP TABLE IF EXISTS spark_catalog.default.sxb_raw;
SQL

docker exec -u root spark-master-41 rm -rf /tmp/sdp-streaming-batch-sql /tmp/sxb-seed 2>/dev/null || true
docker start spark-connect-41 >/dev/null 2>&1 || true

echo "✓ teardown: sdp-streaming-batch-sql complete"
