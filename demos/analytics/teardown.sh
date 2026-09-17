#!/usr/bin/env bash
# Teardown for analytics. Drops the UC table + schema it registered, clears its
# S3 prefix, and removes generated charts. Safe to re-run (idempotent).

set -euo pipefail

DEMO_NAME="analytics"
echo "-> teardown: ${DEMO_NAME}"

# shellcheck source=demos/_lib/s3_cleanup.sh
. "$(dirname "$0")/../_lib/s3_cleanup.sh"

UC_API="${UC_API:-http://localhost:8081/api/2.1/unity-catalog}"
S3_BUCKET="${S3_BUCKET:-lakehouse}"
DEMO_S3_PREFIX="${DEMO_S3_PREFIX:-warehouse/analytics/}"

# --- Drop the UC table then its schema (REST; idempotent) -------------------------
curl -s -o /dev/null -X DELETE "${UC_API}/tables/unity.analytics_demo.sales" || true
curl -s -o /dev/null -X DELETE "${UC_API}/schemas/unity.analytics_demo" || true
echo "  dropped UC table + schema (analytics_demo)"

# --- S3 / object-store prefix cleanup ---------------------------------------------
# An empty/absent prefix is a no-op success; a real failure is fatal.
if clear_s3_prefix "s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"; then
  echo "  cleared s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"
else
  echo "  ERROR: failed to clear s3://${S3_BUCKET}/${DEMO_S3_PREFIX} (check S3 creds/endpoint/daemon)" >&2
  exit 1
fi

# --- Generated charts (script-relative default; matches analytics.py OUTPUT_DIR) --
# Delete only the two known PNGs (never rm -rf an arbitrary LAKEHOUSE_ANALYTICS_OUT),
# then drop the dir if it is now empty.
CHARTS_DIR="${LAKEHOUSE_ANALYTICS_OUT:-$(dirname "$0")/charts}"
rm -f "${CHARTS_DIR}/revenue_by_product_and_region.png" \
      "${CHARTS_DIR}/daily_revenue_trend.png"
rmdir "${CHARTS_DIR}" 2>/dev/null || true
echo "  removed generated charts in ${CHARTS_DIR}"

echo "ok teardown: ${DEMO_NAME} complete"
