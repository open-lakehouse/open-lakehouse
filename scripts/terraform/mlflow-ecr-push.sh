#!/usr/bin/env bash
# mlflow-ecr-push.sh — build the open-lakehouse MLflow tracking-server image
# (ARM64, for Fargate) and push it to Amazon ECR as a tagged release.
#
# The image is the AWS-specific layer in terraform/mlflow-ecs/docker (MLflow
# v3.13.0-full + psql 16 for SNI + the AWS entrypoint). The `-full` base bundles
# psycopg2 + boto3, so Postgres and S3 work out of the box. No secrets are baked
# in. The local stack uses the simpler image in docker/mlflow instead.
#
# Usage:
#   scripts/terraform/mlflow-ecr-push.sh [tag]   # tag overrides MLFLOW_CONTAINER_RELEASE_TAG
#
# Reads (env, ./.env, or ./.env-terraform.mlflow-ecs):
#   AWS_REGION                   target ECR region                        (required)
#   MLFLOW_ECR_REPO              ECR repository name (default open-lakehouse-mlflow)
#   MLFLOW_CONTAINER_RELEASE_TAG default tag when none passed             (default v0.1.0)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Source ./.env (shared) then the recipe-specific ./.env-terraform.mlflow-ecs.
for envfile in .env .env-terraform.mlflow-ecs; do
  if [[ -f "$envfile" ]]; then
    set -a # shellcheck disable=SC1090,SC1091
    source "$envfile"
    set +a
  fi
done

TAG="${1:-${MLFLOW_CONTAINER_RELEASE_TAG:-${MLFLOW_IMAGE_TAG:-v0.1.0}}}"
REGION="${AWS_REGION:-}"
REPO="${MLFLOW_ECR_REPO:-open-lakehouse-mlflow}"

for tool in aws docker; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' is required but not found" >&2; exit 1; }
done
[[ -n "$REGION" ]] || { echo "ERROR: AWS_REGION is not set (env or .env)" >&2; exit 1; }

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${REPO}"

echo "== Ensuring ECR repository '${REPO}' exists in ${REGION} =="
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository \
       --repository-name "$REPO" \
       --region "$REGION" \
       --image-scanning-configuration scanOnPush=true \
       --image-tag-mutability MUTABLE >/dev/null
echo "  repo: ${IMAGE}"

echo "== Logging in to ECR =="
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# The ECS image is the AWS-specific layer in terraform/mlflow-ecs/docker (MLflow
# -full + psql 16 for SNI + the AWS entrypoint). Its Dockerfile COPYs entrypoint.sh
# relative to that directory, so the build context is that directory.
BUILD_CONTEXT="$ROOT/terraform/mlflow-ecs/docker"
echo "== Building + pushing ${IMAGE}:${TAG} (linux/arm64) =="
docker buildx build \
  --platform linux/arm64 \
  -t "${IMAGE}:${TAG}" \
  -t "${IMAGE}:latest" \
  --push \
  "$BUILD_CONTEXT"

echo
echo "Pushed:"
echo "  ${IMAGE}:${TAG}"
echo "  ${IMAGE}:latest"
echo
echo "Image URI for ECS: ${IMAGE}:${TAG}"
