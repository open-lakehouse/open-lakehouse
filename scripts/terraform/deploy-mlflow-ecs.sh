#!/usr/bin/env bash
# deploy-mlflow-ecs.sh — build+push the MLflow image and apply terraform/mlflow-ecs.
#
# Steps:
#   1. Build + push the ARM64 image to ECR (scripts/terraform/mlflow-ecr-push.sh),
#      unless DEPLOY_SKIP_BUILD=1.
#   2. terraform init + apply in terraform/mlflow-ecs.
#   3. Wait for the ECS service to stabilize, then print the tracking-server URL.
#
# Config is layered (later wins): terraform/mlflow-ecs/variables.tf defaults <
# ./.env < ./.env-terraform.mlflow-ecs (mapped onto TF_VAR_* below) < CLI tag arg.
#
# Pre-reqs you must provide before apply:
#   - An existing PostgreSQL endpoint (host/port/db/user). The db + role can be
#     pre-created, or auto-provisioned by the entrypoint if it can reach the
#     server with superuser creds (not the default on a managed RDS).
#   - An existing S3 bucket for artifacts (MLFLOW_ARTIFACT_BUCKET).
#   - The DB password stored in Secrets Manager / SSM; its ARN supplied via
#     MLFLOW_PG_PASSWORD_SECRET_ARN.
#
# Usage:
#   scripts/terraform/deploy-mlflow-ecs.sh [tag]   # tag overrides MLFLOW_CONTAINER_RELEASE_TAG
#
# Knobs:
#   DEPLOY_AUTO_APPROVE=1   skip the interactive `terraform apply` confirmation
#   DEPLOY_SKIP_BUILD=1     skip the image build/push (already pushed for this tag)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TF_DIR="$ROOT/terraform/mlflow-ecs"

# Source ./.env (shared) then the recipe-specific ./.env-terraform.mlflow-ecs.
for envfile in .env .env-terraform.mlflow-ecs; do
  if [[ -f "$envfile" ]]; then
    set -a # shellcheck disable=SC1090,SC1091
    source "$envfile"
    set +a
  fi
done

for tool in aws terraform; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' is required but not found" >&2; exit 1; }
done

# Tag precedence: CLI arg > MLFLOW_CONTAINER_RELEASE_TAG > MLFLOW_IMAGE_TAG > default.
TAG="${1:-${MLFLOW_CONTAINER_RELEASE_TAG:-${MLFLOW_IMAGE_TAG:-v0.1.0}}}"
REGION="${AWS_REGION:-}"
[[ -n "$REGION" ]] || { echo "ERROR: AWS_REGION is not set (env, .env, or .env-terraform.mlflow-ecs)" >&2; exit 1; }

# Map .env-terraform.mlflow-ecs values onto TF_VAR_* (overriding variables.tf
# defaults). Only export when set so terraform.tfvars can still supply the rest.
[[ -n "${MLFLOW_ECR_REPO:-}" ]] && export TF_VAR_ecr_repo_name="$MLFLOW_ECR_REPO"
[[ -n "${MLFLOW_PG_HOST:-}" ]] && export TF_VAR_pg_host="$MLFLOW_PG_HOST"
[[ -n "${MLFLOW_PG_PORT:-}" ]] && export TF_VAR_pg_port="$MLFLOW_PG_PORT"
[[ -n "${MLFLOW_PG_DB:-}" ]] && export TF_VAR_pg_database="$MLFLOW_PG_DB"
[[ -n "${MLFLOW_PG_USER:-}" ]] && export TF_VAR_pg_user="$MLFLOW_PG_USER"
[[ -n "${MLFLOW_PG_ADMIN_DB:-}" ]] && export TF_VAR_pg_admin_db="$MLFLOW_PG_ADMIN_DB"
[[ -n "${MLFLOW_PG_SSLMODE+x}" ]] && export TF_VAR_pg_sslmode="$MLFLOW_PG_SSLMODE"
[[ -n "${MLFLOW_SKIP_PROVISION:-}" ]] && export TF_VAR_skip_provision="$MLFLOW_SKIP_PROVISION"
[[ -n "${MLFLOW_ARTIFACT_BUCKET:-}" ]] && export TF_VAR_artifact_bucket="$MLFLOW_ARTIFACT_BUCKET"
[[ -n "${MLFLOW_ARTIFACT_PREFIX:-}" ]] && export TF_VAR_artifact_prefix="$MLFLOW_ARTIFACT_PREFIX"
[[ -n "${MLFLOW_DOMAIN_NAME:-}" ]] && export TF_VAR_domain_name="$MLFLOW_DOMAIN_NAME"
[[ -n "${MLFLOW_HOSTED_ZONE_ID:-}" ]] && export TF_VAR_hosted_zone_id="$MLFLOW_HOSTED_ZONE_ID"
[[ -n "${MLFLOW_CERT_DOMAIN_NAME:-}" ]] && export TF_VAR_cert_domain_name="$MLFLOW_CERT_DOMAIN_NAME"
[[ -n "${MLFLOW_ALLOWED_HOSTS:-}" ]] && export TF_VAR_allowed_hosts="$MLFLOW_ALLOWED_HOSTS"
[[ -n "${MLFLOW_CORS_ALLOWED_ORIGINS:-}" ]] && export TF_VAR_cors_allowed_origins="$MLFLOW_CORS_ALLOWED_ORIGINS"

# Resolve the DB password secret ARN that the ECS task injects as MLFLOW_PG_PASS.
#   1. If MLFLOW_PG_PASSWORD_SECRET_ARN is set, use it as-is.
#   2. Else, if MLFLOW_PG_PASSWORD is set, create/update a Secrets Manager secret
#      from it (named MLFLOW_PG_SECRET_NAME) and use that ARN. The plaintext only
#      ever lives in your local .env; Terraform only sees the ARN.
SECRET_ARN="${MLFLOW_PG_PASSWORD_SECRET_ARN:-}"
if [[ -z "$SECRET_ARN" ]]; then
  if [[ -n "${MLFLOW_PG_PASSWORD:-}" ]]; then
    SECRET_NAME="${MLFLOW_PG_SECRET_NAME:-mlflow/${MLFLOW_PG_USER:-mlflow}-pwd}"
    echo "== Ensuring Secrets Manager secret '${SECRET_NAME}' from MLFLOW_PG_PASSWORD =="
    if SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" --query ARN --output text 2>/dev/null)"; then
      aws secretsmanager put-secret-value \
        --secret-id "$SECRET_NAME" \
        --secret-string "$MLFLOW_PG_PASSWORD" \
        --region "$REGION" >/dev/null
      echo "  updated existing secret"
    else
      SECRET_ARN="$(aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "MLflow tracking server Postgres password" \
        --secret-string "$MLFLOW_PG_PASSWORD" \
        --region "$REGION" \
        --query ARN --output text)"
      echo "  created secret"
    fi
  else
    echo "ERROR: provide MLFLOW_PG_PASSWORD_SECRET_ARN, or MLFLOW_PG_PASSWORD to auto-create the secret." >&2
    exit 1
  fi
fi
export TF_VAR_pg_password_secret_arn="$SECRET_ARN"

tf_out() { terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null; }

# 1) Build + push the image.
if [[ "${DEPLOY_SKIP_BUILD:-0}" == "1" ]]; then
  echo "== Skipping image build (DEPLOY_SKIP_BUILD=1) =="
else
  echo "== Building + pushing MLflow image (tag ${TAG}) =="
  bash "$ROOT/scripts/terraform/mlflow-ecr-push.sh" "$TAG"
fi

# Pass the tag + region through; let terraform.tfvars provide the rest.
export TF_VAR_image_tag="$TAG"
export TF_VAR_aws_region="$REGION"

# The Terraform AWS provider can't read the AWS CLI v2 SSO/login token cache, so
# materialize the active credentials as env vars when they aren't already set.
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && aws configure export-credentials >/dev/null 2>&1; then
  echo "== Exporting AWS CLI credentials for Terraform =="
  eval "$(aws configure export-credentials --format env)"
fi

# 2) Apply.
echo "== terraform init (terraform/mlflow-ecs) =="
terraform -chdir="$TF_DIR" init -input=false

echo "== terraform apply (terraform/mlflow-ecs) =="
if [[ "${DEPLOY_AUTO_APPROVE:-0}" == "1" ]]; then
  terraform -chdir="$TF_DIR" apply -input=false -auto-approve
else
  terraform -chdir="$TF_DIR" apply -input=false
fi

CLUSTER="$(tf_out cluster_name)"
SERVICE="$(tf_out service_name)"

# 3) Wait for the service to stabilize.
if [[ -n "$CLUSTER" && -n "$SERVICE" ]]; then
  echo "== Waiting for the ECS service to stabilize =="
  aws ecs wait services-stable \
    --cluster "$CLUSTER" \
    --services "$SERVICE" \
    --region "$REGION" || echo "  WARNING: service did not stabilize in time; check the ECS console." >&2
fi

echo
echo "Deployment complete."
echo "  MLflow URL : $(tf_out mlflow_url)"
echo "  Artifacts  : $(tf_out artifacts_destination)"
