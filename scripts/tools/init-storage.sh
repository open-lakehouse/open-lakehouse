#!/usr/bin/env bash
# init-storage.sh — idempotent bootstrap for the Composed storage layer (T-1.8).
#
# Creates (idempotently, safe to re-run):
#   - the S3 bucket ${S3_BUCKET} in SeaweedFS
#   - the warehouse prefixes bronze / silver / gold / _checkpoints / pipeline-history
#   - the iceberg_catalog PostgreSQL database (mlflow / airflow self-provision via
#     their own entrypoints, so they are intentionally NOT created here)
#
# Targets the effective endpoints from the environment (.env is sourced if present),
# defaulting to the published host ports for the default (non-overlay) path.
#
# No host tooling required: S3 uses a host `aws` if present, else a dockerized
# aws-cli; PostgreSQL runs psql INSIDE the postgres container via `docker exec`.
# Requires only a reachable Docker daemon.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Load .env for credentials/endpoints if present (does not override the environment).
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env"
  set +a
fi

S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:8333}"
S3_BUCKET="${S3_BUCKET:-lakehouse}"
# Unified demo credential pair — must match docker-compose-storage.yml defaults,
# .env.example, and the test fallbacks so a fresh clone bootstraps consistently.
S3_ACCESS_KEY="${S3_ACCESS_KEY:-lakehouse_s3}"
S3_SECRET_KEY="${S3_SECRET_KEY:-lakehouse_s3_secret}"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

# This bootstrap runs HOST-side against the published ports, so the container-only
# alias host.docker.internal (still the .env default until the bridge conversion)
# is rewritten to localhost. An overlay/CI run can point these at run-scoped
# endpoints via the environment instead.
S3_ENDPOINT="${S3_ENDPOINT//host.docker.internal/localhost}"
POSTGRES_HOST="${POSTGRES_HOST//host.docker.internal/localhost}"

# Warehouse prefixes to materialize (as zero-byte folder markers).
WAREHOUSE_PREFIXES=(bronze silver gold _checkpoints pipeline-history)

# Databases init-storage owns (others self-provision).
MANAGED_DATABASES=(iceberg_catalog)

log()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }

# AWS CLI wrapper: prefer a host `aws`; fall back to a dockerized aws-cli so
# `start storage` works with no host aws install (same pattern as pg_psql / aws_s3
# in ./lakehouse). The dockerized client reaches the host-published S3 port via the
# host-gateway, so a localhost/loopback endpoint is rewritten to
# host.docker.internal. Override the image with LAKEHOUSE_AWSCLI_IMAGE.
# Pinned aws-cli 2.24.6 (not :latest) for reproducibility — mirrors the repo's
# AWS SDK v2 2.24.6 pin (see CLAUDE.md version pins).
AWSCLI_IMAGE="${LAKEHOUSE_AWSCLI_IMAGE:-amazon/aws-cli:2.24.6}"
awscli() {
  if command -v aws >/dev/null 2>&1; then
    AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" \
    AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" \
    AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
      aws --endpoint-url "${S3_ENDPOINT}" "$@"
  else
    local dep="${S3_ENDPOINT//127.0.0.1/host.docker.internal}"
    dep="${dep//localhost/host.docker.internal}"
    docker run --rm --add-host=host.docker.internal:host-gateway \
      -e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" \
      -e AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" \
      -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
      "${AWSCLI_IMAGE}" \
      --endpoint-url "${dep}" "$@"
  fi
}

# --- S3 -------------------------------------------------------------------
init_s3() {
  echo "SeaweedFS S3 (${S3_ENDPOINT}, bucket ${S3_BUCKET}):"

  # SeaweedFS opens the S3 TCP port a beat before the gateway accepts API calls
  # (a fresh start can briefly close the connection). Wait for real readiness
  # before bootstrapping, so `start storage` is deterministic.
  local i
  for i in 1 2 3 4 5 6 7 8; do
    if awscli s3 ls >/dev/null 2>&1; then
      break
    fi
    if [ "${i}" -eq 8 ]; then
      echo "  S3 endpoint ${S3_ENDPOINT} not ready after retries" >&2
      return 1
    fi
    sleep "${i}"
  done

  # Bucket (idempotent): head-bucket succeeds if it already exists.
  if awscli s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
    log "bucket ${S3_BUCKET} already exists"
  else
    awscli s3api create-bucket --bucket "${S3_BUCKET}" >/dev/null
    ok "created bucket ${S3_BUCKET}"
  fi

  # Warehouse prefixes as folder markers (put-object is idempotent).
  local p key
  for p in "${WAREHOUSE_PREFIXES[@]}"; do
    key="warehouse/${p}/"
    awscli s3api put-object --bucket "${S3_BUCKET}" --key "${key}" >/dev/null
    ok "prefix s3://${S3_BUCKET}/${key}"
  done
}

# --- PostgreSQL -----------------------------------------------------------
# Runs psql INSIDE the postgres container (the client is always present there and
# the storage layer is Compose-managed), so no host psql install is required.
# POSTGRES_CONTAINER overrides the container name for overlay/CI runs.
init_databases() {
  local container="${POSTGRES_CONTAINER:-postgres}"
  echo "PostgreSQL (container ${container}):"

  local psql=(docker exec -e "PGPASSWORD=${POSTGRES_PASSWORD}" "${container}"
              psql -U "${POSTGRES_USER}" -d postgres -tAc)

  local db exists
  for db in "${MANAGED_DATABASES[@]}"; do
    exists="$("${psql[@]}" "SELECT 1 FROM pg_database WHERE datname = '${db}'" 2>/dev/null || true)"
    if [ "${exists//[[:space:]]/}" = "1" ]; then
      log "database ${db} already exists"
    else
      "${psql[@]}" "CREATE DATABASE ${db}" >/dev/null
      ok "created database ${db}"
    fi
  done
}

main() {
  init_s3
  init_databases
  echo "storage bootstrap complete."
}

main "$@"
