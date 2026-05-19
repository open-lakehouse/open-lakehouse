#!/usr/bin/env bash
# Post-start smoke test: write/read/drop an Iceberg table via Spark + UC.
# Verifies the Spark ↔ Unity Catalog ↔ SeaweedFS loop end-to-end.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$PROJECT_ROOT"

NAMESPACE="iceberg.bronze"
TABLE="_smoke_$(date +%s)"
FQN="${NAMESPACE}.${TABLE}"

echo "→ smoke: creating ${FQN}"
docker exec spark-master-41 /opt/spark/bin/spark-sql --silent <<SQL
CREATE NAMESPACE IF NOT EXISTS ${NAMESPACE};
CREATE TABLE ${FQN} (id INT, payload STRING) USING iceberg;
INSERT INTO ${FQN} VALUES (1, 'hello-open-lakehouse');
SELECT * FROM ${FQN};
SQL

echo "→ smoke: verifying via Unity Catalog REST"
if curl -sf "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=iceberg&schema_name=bronze" \
   | grep -q "${TABLE}"; then
    echo "✓ smoke: UC sees ${FQN}"
else
    echo "✗ smoke: UC did not list ${FQN}"
    exit 1
fi

echo "→ smoke: dropping ${FQN}"
docker exec spark-master-41 /opt/spark/bin/spark-sql --silent <<SQL
DROP TABLE ${FQN};
SQL

echo "✓ smoke: complete"
