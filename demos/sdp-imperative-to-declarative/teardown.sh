#!/usr/bin/env bash
# Teardown for sdp-imperative-to-declarative. Safe to re-run.
set -euo pipefail

UC=http://localhost:8081/api/2.1/unity-catalog

echo "→ teardown: sdp-imperative-to-declarative"

# Drop the six UC tables under unity.i2d (idempotent — 404s are fine).
for t in imp_orders_bronze imp_orders_silver imp_orders_gold \
         dec_orders_bronze dec_orders_silver dec_orders_gold; do
  curl -s -X DELETE "${UC}/tables/unity.i2d.${t}" > /dev/null 2>&1 || true
  echo "  dropped unity.i2d.${t}"
done

docker exec -u root spark-master-41 rm -rf \
  /tmp/declarative-medallion-storage /tmp/declarative 2>/dev/null || true
docker start spark-connect-41 >/dev/null 2>&1 || true

echo "✓ teardown: sdp-imperative-to-declarative complete"
echo "  NOTE: Delta files under s3://lakehouse/warehouse/sdp/v2/i2d/ are not"
echo "        deleted. Remove them with an S3 client for a fully clean slate."
