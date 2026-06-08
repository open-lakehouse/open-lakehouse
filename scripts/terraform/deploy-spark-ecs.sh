#!/usr/bin/env bash
# deploy-spark-ecs.sh — build+push the Spark image and apply terraform/spark-ecs.
#
# Steps:
#   1. Build + push the ARM64 image to ECR (scripts/terraform/spark-ecr-push.sh),
#      unless DEPLOY_SKIP_BUILD=1.
#   2. terraform init + apply in terraform/spark-ecs.
#   3. Wait for the ECS services to stabilize, then print the master UI +
#      Spark Connect URLs.
#
# Config is layered (later wins): terraform/spark-ecs/variables.tf defaults <
# ./.env < ./.env-terraform.spark-ecs (mapped onto TF_VAR_* below) < CLI tag arg.
#
# Usage:
#   scripts/terraform/deploy-spark-ecs.sh [tag]   # tag overrides SPARK_CONTAINER_RELEASE_TAG
#
# Knobs:
#   DEPLOY_AUTO_APPROVE=1   skip the interactive `terraform apply` confirmation
#   DEPLOY_SKIP_BUILD=1     skip the image build/push (already pushed for this tag)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TF_DIR="$ROOT/terraform/spark-ecs"

# Source ./.env (shared) then the recipe-specific ./.env-terraform.spark-ecs.
for envfile in .env .env-terraform.spark-ecs; do
  if [[ -f "$envfile" ]]; then
    set -a # shellcheck disable=SC1091
    source "$envfile"
    set +a
  fi
done

for tool in aws terraform; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' is required but not found" >&2; exit 1; }
done

# Tag precedence: CLI arg > SPARK_CONTAINER_RELEASE_TAG > SPARK_IMAGE_TAG > default.
TAG="${1:-${SPARK_CONTAINER_RELEASE_TAG:-${SPARK_IMAGE_TAG:-v0.1.0}}}"
REGION="${AWS_REGION:-}"
[[ -n "$REGION" ]] || { echo "ERROR: AWS_REGION is not set (env, .env, or .env-terraform.spark-ecs)" >&2; exit 1; }

# Map .env-terraform.spark-ecs values onto TF_VAR_* (overriding variables.tf
# defaults). Only export when set so terraform.tfvars can still supply the rest.
[[ -n "${SPARK_CLUSTER_DOMAIN_NAME:-}" ]] && export TF_VAR_domain_name="$SPARK_CLUSTER_DOMAIN_NAME"
[[ -n "${SPARK_CLUSTER_CONNECT_DOMAIN_NAME:-}" ]] && export TF_VAR_connect_domain_name="$SPARK_CLUSTER_CONNECT_DOMAIN_NAME"
[[ -n "${SPARK_CLUSTER_HOSTED_ZONE_ID:-}" ]] && export TF_VAR_hosted_zone_id="$SPARK_CLUSTER_HOSTED_ZONE_ID"
[[ -n "${SPARK_CLUSTER_CERT_DOMAIN_NAME:-}" ]] && export TF_VAR_cert_domain_name="$SPARK_CLUSTER_CERT_DOMAIN_NAME"
[[ -n "${SPARK_ECR_REPO:-}" ]] && export TF_VAR_ecr_repo_name="$SPARK_ECR_REPO"

tf_out() { terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null; }

# 1) Build + push the image.
if [[ "${DEPLOY_SKIP_BUILD:-0}" == "1" ]]; then
  echo "== Skipping image build (DEPLOY_SKIP_BUILD=1) =="
else
  echo "== Building + pushing Spark image (tag ${TAG}) =="
  bash "$ROOT/scripts/terraform/spark-ecr-push.sh" "$TAG"
fi

# Pass the tag through; let terraform.tfvars provide the rest.
export TF_VAR_image_tag="$TAG"
[[ -n "${AWS_REGION:-}" ]] && export TF_VAR_aws_region="$AWS_REGION"

# The Terraform AWS provider can't read the AWS CLI v2 SSO/login token cache, so
# materialize the active credentials as env vars when they aren't already set.
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && aws configure export-credentials >/dev/null 2>&1; then
  echo "== Exporting AWS CLI credentials for Terraform =="
  eval "$(aws configure export-credentials --format env)"
fi

# 2) Apply.
echo "== terraform init (terraform/spark-ecs) =="
terraform -chdir="$TF_DIR" init -input=false

echo "== terraform apply (terraform/spark-ecs) =="
if [[ "${DEPLOY_AUTO_APPROVE:-0}" == "1" ]]; then
  terraform -chdir="$TF_DIR" apply -input=false -auto-approve
else
  terraform -chdir="$TF_DIR" apply -input=false
fi

CLUSTER="$(tf_out cluster_name)"
MASTER_SVC="$(tf_out master_service_name)"
WORKER_SVC="$(tf_out worker_service_name)"

# 3) Wait for the core services to stabilize.
if [[ -n "$CLUSTER" && -n "$MASTER_SVC" ]]; then
  echo "== Waiting for ECS services to stabilize =="
  aws ecs wait services-stable \
    --cluster "$CLUSTER" \
    --services "$MASTER_SVC" "$WORKER_SVC" \
    --region "$REGION" || echo "  WARNING: services did not stabilize in time; check the ECS console." >&2
fi

echo
echo "Deployment complete."
echo "  Master UI : $(tf_out master_ui_url)"
CONNECT_URL="$(tf_out connect_url || true)"
[[ -n "$CONNECT_URL" ]] && echo "  Connect   : $CONNECT_URL"
