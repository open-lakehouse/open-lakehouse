#!/usr/bin/env bash
# Teardown for sdp-cli-lifecycle. Safe to re-run.
set -euo pipefail

echo "→ teardown: sdp-cli-lifecycle"

# Drop the example datasets the generated project created in spark_catalog.
docker exec spark-master-41 /opt/spark/bin/spark-sql --silent <<'SQL' 2>/dev/null || true
DROP TABLE IF EXISTS spark_catalog.default.clife_nums;
DROP TABLE IF EXISTS spark_catalog.default.clife_even;
SQL

# Remove the scaffolded project + its pipeline storage inside the container.
docker exec -u root spark-master-41 rm -rf /tmp/sdp-lifecycle 2>/dev/null || true
docker start spark-connect-41 >/dev/null 2>&1 || true

echo "✓ teardown: sdp-cli-lifecycle complete"
