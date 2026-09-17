#!/usr/bin/env bash
# Teardown for the sdp-medallion demo. Safe to re-run.
#
# The demo materializes CATALOG-MANAGED Delta tables in managed_demo.medallion_demo
# (UC assigns their storage under the catalog's storage_root). Dropping the UC
# tables also releases their managed storage under __unitystorage/.
set -euo pipefail

UC="${UC_HOST:-http://localhost:8081}/api/2.1/unity-catalog"

echo "-> teardown: sdp-medallion"

# Drop the medallion tables (idempotent - 404s are fine). Reverse dependency
# order: gold -> silver -> bronze/dim.
for t in gold_brand_summary gold_hourly_metrics orders_enriched dim_locations orders_bronze; do
  curl -s -X DELETE "${UC}/tables/managed_demo.medallion_demo.${t}" > /dev/null || true
  echo "  dropped managed_demo.medallion_demo.${t}"
done

# Clear the SDP pipeline storage.
rm -rf /tmp/sdp-medallion-storage 2>/dev/null || true

echo "ok teardown: sdp-medallion complete"
echo "  NOTE: catalog-managed table data lived under the catalog storage_root"
echo "        (s3://lakehouse/warehouse/managed/__unitystorage/...). Dropping the"
echo "        UC tables releases it; the seeded inputs under /data are left in place."
