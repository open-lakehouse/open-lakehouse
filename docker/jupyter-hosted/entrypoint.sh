#!/usr/bin/env bash
# Render spark-defaults.conf from the template (injecting UC_TOKEN + warehouse),
# then launch JupyterLab. The SDP subprocess (spark-pipelines) reads this file,
# so the token MUST land here, not just in the notebook session.
set -euo pipefail

: "${UC_TOKEN:=not_used}"
: "${MEDALLION_WAREHOUSE:=s3://uc-quickstart-207734640204-usw2/warehouse/medallion}"
: "${DEMO_NS:=}"
export UC_TOKEN MEDALLION_WAREHOUSE DEMO_NS

envsubst '${UC_TOKEN} ${MEDALLION_WAREHOUSE}' \
  < /opt/spark/conf/spark-defaults.conf.template \
  > /opt/spark/conf/spark-defaults.conf

echo "entrypoint: rendered spark-defaults.conf (DEMO_NS='${DEMO_NS}', warehouse='${MEDALLION_WAREHOUSE}')"
if [ "${UC_TOKEN}" = "not_used" ]; then
  echo "entrypoint: WARNING — UC_TOKEN not set; SDP writes to Scott's UC will 401."
fi

exec jupyter lab \
  --ip=0.0.0.0 --port=8889 --no-browser --allow-root \
  --ServerApp.token="${JUPYTER_TOKEN:-}" \
  --ServerApp.disable_check_xsrf=True \
  --ServerApp.root_dir=/home/jovyan
