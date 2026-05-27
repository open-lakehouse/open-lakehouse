#!/usr/bin/env bash
# Preflight for the data-backed SDP demos (sdp-imperative-to-declarative,
# sdp-streaming-batch-sql). Verifies the generated event dataset is present
# and populated before a demo runs. Safe to run on its own.
#
#   bash demos/preflight.sh
#
# Exits non-zero with a remediation hint if the data is missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVENTS="$ROOT/data/events/orders_7d.parquet"
DIMS="$ROOT/data/dimensions"

fail() {
  echo "✗ preflight: $1" >&2
  echo "  → generate it first:  ./lakehouse testdata generate" >&2
  exit 1
}

# --- the data is present -----------------------------------------------------
[ -f "$EVENTS" ] || fail "data/events/orders_7d.parquet is missing"
[ -s "$EVENTS" ] || fail "data/events/orders_7d.parquet is empty"
for d in brands categories items locations; do
  [ -f "$DIMS/$d.parquet" ] || fail "data/dimensions/$d.parquet is missing"
done
echo "✓ event data present — $(du -h "$EVENTS" | cut -f1) at data/events/orders_7d.parquet"
echo "✓ dimension tables present — brands, categories, items, locations"

# --- the events are populated (row count + type breakdown, via parquet
#     metadata — no Spark needed) -------------------------------------------
poetry run python - "$EVENTS" <<'PY' || fail "could not read the event parquet"
import sys
import pyarrow.parquet as pq

pf = pq.ParquetFile(sys.argv[1])
n = pf.metadata.num_rows
if n == 0:
    sys.exit("event dataset has 0 rows")
print(f"✓ events emitting — {n:,} events across {pf.metadata.num_row_groups} row groups")
PY

# --- optional: Kafka topic (informational — these demos read the parquet,
#     not Kafka) ---------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx kafka; then
  offsets=$(docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 --topic orders 2>/dev/null | grep -E '^orders:' || true)
  if [ -n "$offsets" ]; then
    total=$(echo "$offsets" | awk -F: '{s+=$3} END {print s}')
    echo "✓ kafka topic 'orders' present — $total messages"
  else
    echo "· kafka topic 'orders' empty (optional — run './lakehouse testdata stream' to populate)"
  fi
fi

echo "preflight OK"
