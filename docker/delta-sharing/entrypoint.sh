#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Containerized Lakehouse Platform Contributors
set -e

echo "Starting OpenSharing Server with URL Rewriter Proxy..." >&2

# Generate self-signed SSL certificate if it doesn't exist or is not readable
if [ ! -f /opt/delta-sharing/certs/server.crt ] || [ ! -r /opt/delta-sharing/certs/server.key ]; then
    echo "Generating self-signed SSL certificate..." >&2
    mkdir -p /opt/delta-sharing/certs

    openssl req -x509 -newkey rsa:4096 \
        -keyout /opt/delta-sharing/certs/server.key \
        -out /opt/delta-sharing/certs/server.crt \
        -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Lakehouse/CN=delta-sharing" 2>/dev/null

    chmod 600 /opt/delta-sharing/certs/server.key
    chmod 644 /opt/delta-sharing/certs/server.crt

    # Validate the generated certificate
    openssl x509 -in /opt/delta-sharing/certs/server.crt -noout 2>/dev/null || {
        echo "ERROR: Generated SSL certificate is invalid" >&2
        exit 1
    }

    echo "✓ SSL certificate generated" >&2
fi

# Set default token if not provided
if [ -z "$DELTA_SHARING_TOKEN" ]; then
    export DELTA_SHARING_TOKEN="$(openssl rand -hex 32)"
    echo "WARNING: No DELTA_SHARING_TOKEN set, generated random token" >&2
fi

# Validate required environment variables
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID must be set}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY must be set}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Ensure log directory exists
mkdir -p /var/log/delta-sharing

# Set Hadoop configuration directory
export HADOOP_CONF_DIR="/opt/delta-sharing/conf"

# Get the public S3 endpoint from environment (allows runtime configuration).
# Default = the host-published SeaweedFS port, so sharing works locally with no
# tunnel; override S3_PUBLIC_ENDPOINT (+ S3_PUBLIC_SCHEME=https) for a public tunnel.
export S3_PUBLIC_ENDPOINT="${S3_PUBLIC_ENDPOINT:-localhost:8333}"
export S3_PUBLIC_SCHEME="${S3_PUBLIC_SCHEME:-http}"

# Process config templates - substitute placeholders with env var values
echo "Processing configuration templates..." >&2
mkdir -p /opt/delta-sharing/runtime

# Process server.yaml: substitute credentials and token
cp /opt/delta-sharing/conf/server.yaml /opt/delta-sharing/runtime/server.yaml
sed -i \
    -e "s|__S3_ACCESS_KEY__|${AWS_ACCESS_KEY_ID}|g" \
    -e "s|__S3_SECRET_KEY__|${AWS_SECRET_ACCESS_KEY}|g" \
    -e "s|__DELTA_SHARING_TOKEN__|${DELTA_SHARING_TOKEN}|g" \
    /opt/delta-sharing/runtime/server.yaml

# Validate that credential placeholders were replaced in server.yaml
if grep -q '__S3_ACCESS_KEY__\|__S3_SECRET_KEY__' /opt/delta-sharing/runtime/server.yaml; then
    echo "ERROR: Failed to substitute credential placeholders in server.yaml" >&2
    exit 1
fi

# Process core-site.xml: substitute credentials
# NOTE: Must also substitute in /opt/delta-sharing/conf/ because the JVM classpath
# includes that directory. The Delta Kernel loads core-site.xml from the classpath
# independently of HADOOP_CONF_DIR, so placeholders there cause S3 auth failures.
cp /opt/delta-sharing/conf/core-site.xml /opt/delta-sharing/runtime/core-site.xml
for f in /opt/delta-sharing/runtime/core-site.xml /opt/delta-sharing/conf/core-site.xml; do
    sed -i \
        -e "s|__S3_ACCESS_KEY__|${AWS_ACCESS_KEY_ID}|g" \
        -e "s|__S3_SECRET_KEY__|${AWS_SECRET_ACCESS_KEY}|g" \
        "$f" 2>/dev/null || true
done

# Validate that credential placeholders were replaced in core-site.xml
if grep -q '__S3_ACCESS_KEY__\|__S3_SECRET_KEY__' /opt/delta-sharing/runtime/core-site.xml; then
    echo "ERROR: Failed to substitute credential placeholders in core-site.xml" >&2
    exit 1
fi

# Process aws-config: substitute the public S3 endpoint
cp /opt/delta-sharing/conf/aws-config /opt/delta-sharing/runtime/aws-config
sed -i \
    -e "s|__S3_PUBLIC_URL__|${S3_PUBLIC_SCHEME}://${S3_PUBLIC_ENDPOINT}|g" \
    /opt/delta-sharing/runtime/aws-config
export AWS_CONFIG_FILE="/opt/delta-sharing/runtime/aws-config"

# Point Hadoop to runtime configs
export HADOOP_CONF_DIR="/opt/delta-sharing/runtime"

# Update server port to 8444 (internal, proxy sits on 8443)
sed -i 's/port: 8443/port: 8444/' /opt/delta-sharing/runtime/server.yaml

echo "OpenSharing Server Configuration:" >&2
echo "  - Upstream Port: 8444 (internal, HTTPS)" >&2
echo "  - Proxy Port: 8443 (external, HTTPS)" >&2
echo "  - Storage: SeaweedFS at http://seaweedfs:8333" >&2
echo "  - Public S3 Endpoint: ${S3_PUBLIC_SCHEME}://${S3_PUBLIC_ENDPOINT}" >&2
echo "  - URL Rewriting: *.s3.amazonaws.com → ${S3_PUBLIC_ENDPOINT}" >&2
echo "  - Shares: lakehouse_share" >&2
echo "  - Hadoop Config: $HADOOP_CONF_DIR" >&2
echo "" >&2

# Trap SIGTERM/SIGINT to cleanly stop both background processes.
cleanup() {
    echo "Received shutdown signal, stopping..." >&2
    [ -n "$PROXY_PID" ] && kill "$PROXY_PID" 2>/dev/null || true
    if [ -n "$DELTA_SHARING_PID" ]; then
        kill "$DELTA_SHARING_PID" 2>/dev/null || true
        wait "$DELTA_SHARING_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start OpenSharing server on internal port in background
echo "Starting upstream OpenSharing server on port 8444..." >&2
java -cp "/opt/delta-sharing/conf:/opt/delta-sharing/lib/*" \
    io.delta.sharing.server.DeltaSharingService \
    --config /opt/delta-sharing/runtime/server.yaml \
    > /var/log/delta-sharing/server.log 2>&1 &

DELTA_SHARING_PID=$!
echo "✓ OpenSharing server started (PID: $DELTA_SHARING_PID)" >&2

# Wait for OpenSharing server to be ready
echo "Waiting for upstream server to be ready..." >&2
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -ks https://localhost:8444/delta-sharing/ > /dev/null 2>&1; then
        echo "✓ Upstream server is ready" >&2
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done

if [ $attempt -ge $max_attempts ]; then
    echo "WARNING: Upstream server may not be fully ready" >&2
fi

# Start the URL rewriter proxy on external port 8443. Run it as a background job
# and `wait` (NOT `exec`) so the SIGTERM/SIGINT trap above stays installed — `exec`
# would replace this shell and discard the trap, leaving the Java server to be
# force-killed on `docker stop`. This way cleanup() stops both processes.
echo "Starting URL rewriter proxy on port 8443..." >&2
python3 /usr/local/bin/url-rewriter-proxy.py &
PROXY_PID=$!
wait "$PROXY_PID"
