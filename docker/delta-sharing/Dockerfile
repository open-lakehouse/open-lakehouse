# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Containerized Lakehouse Platform Contributors

# OpenSharing Server - Multi-stage build using pre-resolved Maven artifacts
# Uses coursier to fetch JARs from Maven proxy (works behind corporate VPN)
# Based on: https://github.com/delta-io/delta-sharing

# Build stage: download JARs and launch script (no sbt compilation needed)
FROM eclipse-temurin:11-jdk-jammy AS builder

ARG DELTA_SHARING_VERSION=1.3.10
ARG MAVEN_REPO_URL=https://repo1.maven.org/maven2

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Download coursier (standalone dependency resolver, ~56MB, from GitHub)
RUN curl -sL -o /usr/local/bin/cs \
    "https://github.com/coursier/launchers/raw/master/cs-$(uname -m)-pc-linux" \
    && chmod +x /usr/local/bin/cs

# Fetch all OpenSharing server JARs from Maven repository
# Uses --no-default to route ALL downloads through the specified repo
# (Maven Central is blocked on some corporate VPNs)
RUN mkdir -p /opt/delta-sharing/lib \
    && cs fetch --no-default \
       --repository "${MAVEN_REPO_URL%/}/" \
       --force-version "io.grpc:grpc-core:1.41.1" \
       --force-version "io.grpc:grpc-api:1.41.1" \
       --force-version "io.grpc:grpc-context:1.41.1" \
       --force-version "io.grpc:grpc-stub:1.41.1" \
       --force-version "io.grpc:grpc-protobuf:1.41.1" \
       --force-version "io.grpc:grpc-protobuf-lite:1.41.1" \
       --force-version "io.grpc:grpc-services:1.41.1" \
       --force-version "io.grpc:grpc-grpclb:1.41.1" \
       --force-version "io.grpc:grpc-netty-shaded:1.41.1" \
       "io.delta:delta-sharing-server_2.12:${DELTA_SHARING_VERSION}" \
       | xargs -I{} cp {} /opt/delta-sharing/lib/ \
    && ls /opt/delta-sharing/lib/delta-sharing-server_2.12-${DELTA_SHARING_VERSION}.jar \
       || { echo "ERROR: delta-sharing-server JAR not resolved from ${MAVEN_REPO_URL%/} — aborting build" >&2; exit 1; }

# Download additional dependencies not in the POM (required for file listing)
RUN curl -fSL -o /opt/delta-sharing/lib/delta-standalone_2.12-3.1.0.jar \
    "${MAVEN_REPO_URL%/}/io/delta/delta-standalone_2.12/3.1.0/delta-standalone_2.12-3.1.0.jar" \
    && curl -fSL -o /opt/delta-sharing/lib/shapeless_2.12-2.3.10.jar \
    "${MAVEN_REPO_URL%/}/com/chuusai/shapeless_2.12/2.3.10/shapeless_2.12-2.3.10.jar"

# Create the bin/ wrapper script that sets classpath from lib/
RUN mkdir -p /opt/delta-sharing/bin \
    && printf '#!/bin/bash\nexec java -cp "/opt/delta-sharing/lib/*" io.delta.sharing.server.DeltaSharingService "$@"\n' \
       > /opt/delta-sharing/bin/delta-sharing-server \
    && chmod +x /opt/delta-sharing/bin/delta-sharing-server

# Create directories
RUN mkdir -p /opt/delta-sharing/conf \
    /opt/delta-sharing/certs \
    /opt/delta-sharing/runtime \
    /var/log/delta-sharing

# Runtime stage: minimal image with only JRE
FROM eclipse-temurin:11-jre-jammy

ARG PIP_INDEX_URL=

# Install only runtime dependencies. The proxy needs `requests`; honor
# PIP_INDEX_URL when supplied (public default otherwise) so the image builds
# behind a package proxy — matches this repo's build-arg convention (T-6.2).
RUN apt-get update && apt-get install -y \
    curl \
    openssl \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} requests

# Create non-root user
RUN groupadd -r deltasharing && \
    useradd -r -g deltasharing -d /opt/delta-sharing -s /sbin/nologin deltasharing

# Copy built artifacts from builder
COPY --from=builder /opt/delta-sharing /opt/delta-sharing

# Copy configuration files
COPY server.yaml /opt/delta-sharing/conf/server.yaml
COPY core-site.xml /opt/delta-sharing/conf/core-site.xml
COPY AwsConfig.properties /opt/delta-sharing/conf/AwsConfig.properties
COPY aws-config /opt/delta-sharing/conf/aws-config
COPY url-rewriter-proxy.py /usr/local/bin/url-rewriter-proxy.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/url-rewriter-proxy.py

# Create runtime directories and set ownership for non-root user
RUN mkdir -p /var/log/delta-sharing \
    && chown -R deltasharing:deltasharing /opt/delta-sharing /var/log/delta-sharing

# Environment
ENV DELTA_SHARING_HOME=/opt/delta-sharing
ENV PATH=$PATH:$DELTA_SHARING_HOME/bin
ENV HADOOP_CONF_DIR=$DELTA_SHARING_HOME/conf

# Switch to non-root user
USER deltasharing

# Expose OpenSharing port (HTTPS)
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=60s \
    CMD curl -ks -o /dev/null -w '%{http_code}' https://localhost:8443/delta-sharing/ | grep -q '401\|200' || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["server"]
