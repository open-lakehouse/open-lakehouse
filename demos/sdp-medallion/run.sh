#!/usr/bin/env bash
# One-command runner for the sdp-medallion demo (catalog-managed Delta).
#
# Encapsulates the moving parts so the demo runs against a clean local stack:
#   1. ensures the `managed_demo` UC catalog exists WITH a storage_root
#      (catalog-managed Delta assigns table locations under it),
#   2. seeds a tiny self-contained input dataset (seed.py -> /data),
#   3. installs the spark-pipelines Python deps into spark-master (the stock
#      apache/spark image ships none),
#   4. runs `spark-pipelines` with a conf that DROPS spark.master (spark-pipelines
#      uses its own embedded Connect driver — spark.master + --remote conflict),
#      after freeing port 15002 by stopping the standalone Connect server.
#
# Requires: Delta 4.3.1 + the UC 0.5.x connector family (see spark-defaults) and
# `./lakehouse start all && ./lakehouse start unity-catalog`.
#
# Behind a firewall, export PIP_INDEX_URL=<mirror>/simple for step 3.
set -euo pipefail

MASTER=spark-master-41
CONNECT=spark-connect-41
UC_HOST="${UC_HOST:-http://localhost:8081}"
UC_API="${UC_HOST}/api/2.1/unity-catalog"
STORAGE_ROOT="${MEDALLION_STORAGE_ROOT:-s3://lakehouse/warehouse/managed}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"

echo "-> 1. ensure managed_demo catalog (storage_root=${STORAGE_ROOT}) + schema"
curl -s -o /dev/null -X POST "${UC_API}/catalogs" -H 'Content-Type: application/json' \
  -d "{\"name\":\"managed_demo\",\"comment\":\"catalog-managed Delta demo\",\"storage_root\":\"${STORAGE_ROOT}\"}" || true
curl -s -o /dev/null -X POST "${UC_API}/schemas" -H 'Content-Type: application/json' \
  -d '{"name":"medallion_demo","catalog_name":"managed_demo"}' || true

echo "-> 1b. drop any prior medallion tables (SDP can't ALTER an existing UC table on re-run)"
for t in gold_brand_summary gold_hourly_metrics orders_enriched dim_locations orders_bronze; do
  curl -s -o /dev/null -X DELETE "${UC_API}/tables/managed_demo.medallion_demo.${t}" || true
done

echo "-> 2. seed input dataset"
docker cp "$(dirname "$0")" "${MASTER}:/tmp/sdp-medallion" >/dev/null
# The seed must actually complete — a silent `|| true` here would let the pipeline
# run against missing input and fail confusingly downstream.
seed_out="$(docker exec "${MASTER}" /opt/spark/bin/spark-submit /tmp/sdp-medallion/seed.py 2>&1)" || true
if ! grep -qE "seed complete" <<<"${seed_out}"; then
  echo "   x seed did not complete — aborting:" >&2
  echo "${seed_out}" | tail -20 >&2
  exit 1
fi
echo "   seed complete"

echo "-> 3. ensure spark-pipelines deps in ${MASTER}"
# Fail loudly if the deps don't install — otherwise spark-pipelines dies later with
# a confusing missing-module error (unlike the UC create/delete calls below, this is
# not an expected-409/404 no-op).
if ! docker exec "${MASTER}" pip install --quiet --index-url "${PIP_INDEX_URL}" \
  --target /tmp/pylibs pyyaml pandas pyarrow grpcio grpcio-status protobuf zstandard; then
  echo "   x failed to install spark-pipelines deps into ${MASTER} — aborting" >&2
  exit 1
fi

echo "-> 4. run the pipeline (spark-pipelines, spark.master stripped)"
docker stop "${CONNECT}" >/dev/null 2>&1 || true
# Restore Connect on ANY exit — success, error (set -e), or interrupt (Ctrl-C /
# TERM). SDP golden rule: never leave the Connect server down. (SIGKILL can't be
# trapped; nothing can help there.)
trap 'docker start "${CONNECT}" >/dev/null 2>&1 || true' EXIT INT TERM
docker exec "${MASTER}" sh -c '
  mkdir -p /tmp/pconf
  grep -v "^spark.master " /opt/spark/conf/spark-defaults.conf > /tmp/pconf/spark-defaults.conf
  [ -f /opt/spark/conf/log4j2.properties ] && cp /opt/spark/conf/log4j2.properties /tmp/pconf/ || true
'
docker exec "${MASTER}" sh -c \
  'cd /tmp/sdp-medallion && SPARK_CONF_DIR=/tmp/pconf PYTHONPATH=/tmp/pylibs:$PYTHONPATH /opt/spark/bin/spark-pipelines run'

echo "-> done. Tables in managed_demo.medallion_demo:"
curl -s "${UC_API}/tables?catalog_name=managed_demo&schema_name=medallion_demo" \
  | python3 -c "import sys,json;[print('   ',t['name'],t['data_source_format']) for t in json.load(sys.stdin).get('tables',[])]" || true
