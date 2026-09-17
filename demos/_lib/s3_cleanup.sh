#!/usr/bin/env bash
# Shared S3 cleanup helper for demo teardown scripts. Source it, then call
# clear_s3_prefix <s3-uri>. Works with no host aws install (dockerized fallback).
#
#   source "$(dirname "$0")/../_lib/s3_cleanup.sh"
#   clear_s3_prefix "s3://lakehouse/warehouse/<demo>/" || exit 1
#
# Reads S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, AWS_DEFAULT_REGION,
# LAKEHOUSE_AWSCLI_IMAGE from the environment (with local-stack defaults).

# aws wrapper: host `aws` if present, else a dockerized aws-cli (same pattern as
# scripts/tools/init-storage.sh) — pinned to mirror the repo's AWS SDK version. The
# dockerized client reaches the host-published S3 port via the host-gateway, so a
# localhost/loopback endpoint is rewritten to host.docker.internal.
awscli() {
  local endpoint="${S3_ENDPOINT:-http://localhost:8333}"
  local image="${LAKEHOUSE_AWSCLI_IMAGE:-amazon/aws-cli:2.24.6}"
  if command -v aws >/dev/null 2>&1; then
    AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY:-lakehouse_s3}" \
    AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY:-lakehouse_s3_secret}" \
    AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
      aws --endpoint-url "${endpoint}" "$@"
  else
    local dep="${endpoint//127.0.0.1/host.docker.internal}"
    dep="${dep//localhost/host.docker.internal}"
    docker run --rm --add-host=host.docker.internal:host-gateway \
      -e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY:-lakehouse_s3}" \
      -e AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY:-lakehouse_s3_secret}" \
      -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
      "${image}" --endpoint-url "${dep}" "$@"
  fi
}

# clear_s3_prefix <s3-uri>: recursively delete the prefix. An empty/absent prefix is
# a no-op success (rc 0); a real failure (bad creds, unreachable endpoint/daemon)
# returns non-zero so the caller can fail loudly. stdout (the per-key delete log) is
# suppressed as noise, but stderr is NOT — a real error stays visible for diagnosis.
clear_s3_prefix() {
  awscli s3 rm "$1" --recursive >/dev/null
}
