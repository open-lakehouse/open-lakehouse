#!/usr/bin/env bash
# Teardown for quick-start. Drops the UC table + schema it registered and clears
# its S3 prefix. Safe to re-run (idempotent).

set -euo pipefail

DEMO_NAME="quick-start"
echo "-> teardown: ${DEMO_NAME}"

# shellcheck source=demos/_lib/s3_cleanup.sh
. "$(dirname "$0")/../_lib/s3_cleanup.sh"

UC_API="${UC_API:-http://localhost:8081/api/2.1/unity-catalog}"
S3_BUCKET="${S3_BUCKET:-lakehouse}"
DEMO_S3_PREFIX="${DEMO_S3_PREFIX:-warehouse/quick-start/}"

# --- Drop the UC table then its schema (REST; idempotent) -------------------------
curl -s -o /dev/null -X DELETE "${UC_API}/tables/unity.quickstart.products" || true
curl -s -o /dev/null -X DELETE "${UC_API}/schemas/unity.quickstart" || true
echo "  dropped UC table + schema (quickstart)"

# --- S3 / object-store prefix cleanup ---------------------------------------------
# An empty/absent prefix is a no-op success; a real failure is fatal (zero residue).
if clear_s3_prefix "s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"; then
  echo "  cleared s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"
else
  echo "  ERROR: failed to clear s3://${S3_BUCKET}/${DEMO_S3_PREFIX} (check S3 creds/endpoint/daemon)" >&2
  exit 1
fi

echo "ok teardown: ${DEMO_NAME} complete"
