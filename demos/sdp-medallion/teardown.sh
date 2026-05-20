#!/usr/bin/env bash
# Teardown for the sdp-medallion demo. Safe to re-run.
set -euo pipefail

UC=http://localhost:8081/api/2.1/unity-catalog

echo "→ teardown: sdp-medallion"

# Drop the three UC tables (idempotent — 404s are fine)
for t in orders_bronze orders_silver orders_gold; do
  curl -s -X DELETE "${UC}/tables/unity.bronze.${t}" > /dev/null || true
  echo "  dropped unity.bronze.${t}"
done

# Clear the SDP pipeline storage + the Delta files on SeaweedFS prefix.
# (SeaweedFS prefix delete is left manual — see README; the warehouse path is
# s3://lakehouse/warehouse/sdp/.)
rm -rf /tmp/sdp-medallion-storage 2>/dev/null || true

echo "✓ teardown: sdp-medallion complete"
echo "  NOTE: Delta files under s3://lakehouse/warehouse/sdp/ are not deleted."
echo "        Remove them with an S3 client if you want a fully clean slate."
