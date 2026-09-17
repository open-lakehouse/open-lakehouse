#!/usr/bin/env bash
# Teardown for unity-catalog. Drops the UC tables + schemas this demo registered
# and clears its S3 prefix. Safe to re-run (idempotent).

set -euo pipefail

DEMO_NAME="unity-catalog"
echo "-> teardown: ${DEMO_NAME}"

# shellcheck source=demos/_lib/s3_cleanup.sh
. "$(dirname "$0")/../_lib/s3_cleanup.sh"

UC_API="${UC_API:-http://localhost:8081/api/2.1/unity-catalog}"
S3_BUCKET="${S3_BUCKET:-lakehouse}"
DEMO_S3_PREFIX="${DEMO_S3_PREFIX:-warehouse/unity-catalog/}"

# --- Drop UC-registered tables, then their schemas (REST; idempotent) -------------
# Tables must go before their schema. 404s (already gone) are fine.
for t in unity.uc_demo_core.dim_regions unity.uc_demo_core.orders \
         unity.uc_demo_analytics.revenue_by_region; do
  curl -s -o /dev/null -X DELETE "${UC_API}/tables/${t}" || true
done
for s in unity.uc_demo_core unity.uc_demo_analytics; do
  curl -s -o /dev/null -X DELETE "${UC_API}/schemas/${s}" || true
done
echo "  dropped UC tables + schemas (uc_demo_core, uc_demo_analytics)"

# --- S3 / object-store prefix cleanup ---------------------------------------------
# An empty/absent prefix is a no-op success; a real failure is fatal.
if clear_s3_prefix "s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"; then
  echo "  cleared s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"
else
  echo "  ERROR: failed to clear s3://${S3_BUCKET}/${DEMO_S3_PREFIX} (check S3 creds/endpoint/daemon)" >&2
  exit 1
fi

echo "ok teardown: ${DEMO_NAME} complete"
