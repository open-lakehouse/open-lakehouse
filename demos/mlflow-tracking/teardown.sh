#!/usr/bin/env bash
# Teardown for mlflow-tracking. Deletes the registered model and the experiment
# via the MLflow REST API and clears the experiment's S3 artifacts. Safe to
# re-run (idempotent; the demo restores a soft-deleted experiment on next run).

set -euo pipefail

DEMO_NAME="mlflow-tracking"
echo "-> teardown: ${DEMO_NAME}"

# Point the shared S3 helper at the MLflow artifact store before sourcing it.
export S3_ENDPOINT="${MLFLOW_S3_ENDPOINT_URL:-http://localhost:8333}"
export S3_ACCESS_KEY="${AWS_ACCESS_KEY_ID:-lakehouse_s3}"
export S3_SECRET_KEY="${AWS_SECRET_ACCESS_KEY:-lakehouse_s3_secret}"
# shellcheck source=demos/_lib/s3_cleanup.sh
. "$(dirname "$0")/../_lib/s3_cleanup.sh"

MLFLOW_API="${MLFLOW_TRACKING_URI:-http://localhost:5000}/api/2.0/mlflow"
EXPERIMENT="lakehouse-revenue-prediction"
MODEL_NAME="lakehouse-revenue-predictor"

# --- Delete the registered model (REST; idempotent) -------------------------------
curl -s -o /dev/null -X DELETE "${MLFLOW_API}/registered-models/delete" \
  -H 'Content-Type: application/json' -d "{\"name\":\"${MODEL_NAME}\"}" || true
echo "  deleted registered model ${MODEL_NAME}"

# --- Look up the experiment (id + artifact location), then delete it --------------
resp="$(curl -s "${MLFLOW_API}/experiments/get-by-name?experiment_name=${EXPERIMENT}" || true)"
exp_id="$(printf '%s' "${resp}" | python3 -c 'import sys,json;
try: print(json.load(sys.stdin)["experiment"]["experiment_id"])
except Exception: print("")' 2>/dev/null || true)"
artifact_loc="$(printf '%s' "${resp}" | python3 -c 'import sys,json;
try: print(json.load(sys.stdin)["experiment"]["artifact_location"])
except Exception: print("")' 2>/dev/null || true)"

if [ -n "${exp_id}" ]; then
  curl -s -o /dev/null -X POST "${MLFLOW_API}/experiments/delete" \
    -H 'Content-Type: application/json' -d "{\"experiment_id\":\"${exp_id}\"}" || true
  echo "  deleted experiment ${EXPERIMENT} (id ${exp_id})"
else
  echo "  experiment ${EXPERIMENT} not found (already gone)"
fi

# --- Clear the experiment's S3 artifacts (zero residue) ---------------------------
# artifact_location looks like s3://lakehouse/mlflow-artifacts/<exp_id>. If the
# experiment was already gone there is nothing to clear. A real S3 failure is fatal.
if [ -n "${artifact_loc}" ]; then
  s3_uri="${artifact_loc%/}/"
  if clear_s3_prefix "${s3_uri}"; then
    echo "  cleared ${s3_uri}"
  else
    echo "  ERROR: failed to clear ${s3_uri} (check S3 creds/endpoint/daemon)" >&2
    exit 1
  fi
fi

echo "ok teardown: ${DEMO_NAME} complete"
