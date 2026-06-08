#!/usr/bin/env bash
# Render spark-defaults.conf from the template (injecting UC_TOKEN), namespace
# the SDP pipeline to this presenter, ensure the UC schema exists, then launch
# JupyterLab. The SDP CLI (spark-pipelines) reads spark-defaults.conf, so the
# token MUST land there. Namespacing here keeps the notebook to plain
# `!spark-pipelines run` commands.
set -euo pipefail

: "${UC_TOKEN:=not_used}"
: "${MEDALLION_WAREHOUSE:=s3://uc-quickstart-207734640204-usw2/warehouse/medallion}"
: "${DEMO_NS:=}"
: "${SDP_DEMO_DIR:=/home/jovyan/demos/sdp-medallion}"
export UC_TOKEN MEDALLION_WAREHOUSE

envsubst '${UC_TOKEN} ${MEDALLION_WAREHOUSE}' \
  < /opt/spark/conf/spark-defaults.conf.template \
  > /opt/spark/conf/spark-defaults.conf

# Per-presenter schema (strip a trailing underscore; default for a bare image).
NS="${DEMO_NS%_}"; NS="${NS:-medallion_demo}"; export NS
SPEC="${SDP_DEMO_DIR}/spark-pipeline.yml"
[ -f "$SPEC" ] && sed -i "s/^schema:.*/schema: ${NS}/" "$SPEC"

echo "entrypoint: schema='${NS}', spark-defaults rendered"
if [ "${UC_TOKEN}" = "not_used" ]; then
  echo "entrypoint: WARNING - UC_TOKEN not set; SDP writes to UC will 401."
fi

# Ensure the presenter's UC schema exists and start from a clean slate (UC has
# no TRUNCATE, so a stale table would fail a re-run). Best-effort; never blocks.
python3 - <<'PYEOF' || true
import os, json, urllib.request
ns = os.environ["NS"]; tok = os.environ.get("UC_TOKEN", "")
base = "https://uc.openlakehousedemos.dev/api/2.1/unity-catalog"
hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
def req(url, method, data=None):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method=method, data=data, headers=hdr), timeout=15)
    except Exception:
        pass
req(f"{base}/schemas", "POST", json.dumps({"name": ns, "catalog_name": "managed_demo"}).encode())
for t in ("gold_brand_summary","gold_hourly_metrics","orders_enriched","orders_bronze","dim_locations"):
    req(f"{base}/tables/managed_demo.{ns}.{t}", "DELETE")
PYEOF

exec jupyter lab \
  --ip=0.0.0.0 --port=8889 --no-browser --allow-root \
  --ServerApp.token="${JUPYTER_TOKEN:-}" \
  --ServerApp.disable_check_xsrf=True \
  --ServerApp.root_dir=/home/jovyan
