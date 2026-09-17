#!/usr/bin/env bash
# Teardown for delta-deep-dive. Removes every artifact the demo created.
# Safe to re-run (idempotent).

set -euo pipefail

DEMO_NAME="delta-deep-dive"
echo "-> teardown: ${DEMO_NAME}"

# shellcheck source=demos/_lib/s3_cleanup.sh
. "$(dirname "$0")/../_lib/s3_cleanup.sh"

S3_BUCKET="${S3_BUCKET:-lakehouse}"
DEMO_S3_PREFIX="${DEMO_S3_PREFIX:-warehouse/delta-deep-dive/}"

# --- S3 / object-store prefix cleanup ---------------------------------------------
# The demo writes a path-based Delta table under this prefix (no UC table to drop).
# An empty/absent prefix is a no-op success; a real failure is fatal.
if clear_s3_prefix "s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"; then
  echo "  cleared s3://${S3_BUCKET}/${DEMO_S3_PREFIX}"
else
  echo "  ERROR: failed to clear s3://${S3_BUCKET}/${DEMO_S3_PREFIX} (check S3 creds/endpoint/daemon)" >&2
  exit 1
fi

echo "ok teardown: ${DEMO_NAME} complete"
