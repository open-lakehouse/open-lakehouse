#!/usr/bin/env bash
# spark-ecr-push.sh — build the open-lakehouse Spark 4.1 standalone image (ARM64,
# for Fargate) and push it to Amazon ECR as a tagged release.
#
# The image is the thin custom layer in terraform/spark-ecs/docker (Apache Spark
# 4.1 + lakehouse JARs + entrypoint). Built for linux/arm64 to match the Fargate
# ARM64 runtime (and local Apple Silicon). No secrets are baked in.
#
# Usage:
#   scripts/terraform/spark-ecr-push.sh [tag]   # tag overrides SPARK_CONTAINER_RELEASE_TAG
#
# Reads (env, ./.env, or ./.env-terraform.spark-ecs):
#   AWS_REGION                  target ECR region                       (required)
#   SPARK_ECR_REPO              ECR repository name (default open-lakehouse-spark)
#   SPARK_CONTAINER_RELEASE_TAG default tag when none passed            (default v0.1.0)
#   MAVEN_PROXY_URL             Maven mirror for the JAR downloads      (optional)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Source ./.env (shared) then the recipe-specific ./.env-terraform.spark-ecs.
for envfile in .env .env-terraform.spark-ecs; do
  if [[ -f "$envfile" ]]; then
    set -a # shellcheck disable=SC1091
    source "$envfile"
    set +a
  fi
done

TAG="${1:-${SPARK_CONTAINER_RELEASE_TAG:-${SPARK_IMAGE_TAG:-v0.1.0}}}"
REGION="${AWS_REGION:-}"
REPO="${SPARK_ECR_REPO:-open-lakehouse-spark}"
MAVEN_PROXY_URL="${MAVEN_PROXY_URL:-https://repo1.maven.org/maven2}"
BUILD_CONTEXT="$ROOT/terraform/spark-ecs/docker"

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

echo "== Building + pushing ${IMAGE}:${TAG} (linux/arm64) =="
docker buildx build \
  --platform linux/arm64 \
  --build-arg MAVEN_PROXY_URL="$MAVEN_PROXY_URL" \
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
