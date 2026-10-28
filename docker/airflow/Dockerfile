# Airflow 3.1.6 with Python 3.12 and the stack's pinned Spark distribution.
FROM apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu AS spark-runtime

FROM apache/airflow:3.1.6-python3.12

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ARG SPARK_DIST_URL=

USER root

# Install system dependencies using the base image's Debian repositories.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    openjdk-17-jre-headless \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "/usr/lib/jvm/java-17-openjdk-$(dpkg --print-architecture)" /opt/java

# Resolve Java for both Apple Silicon (arm64) and x86 hosts.
ENV JAVA_HOME=/opt/java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Reuse the pinned distribution instead of downloading it again from the archive.
# A custom distribution URL remains available for package-proxy environments.
ENV SPARK_VERSION=4.1.0
ENV SPARK_HOME=/opt/spark
COPY --from=spark-runtime --chown=airflow:root /opt/spark /opt/spark
RUN if [ -n "$SPARK_DIST_URL" ]; then \
      curl -fsSL "$SPARK_DIST_URL" | tar -xz -C /tmp/ \
      && rm -rf "$SPARK_HOME" \
      && mv "/tmp/spark-${SPARK_VERSION}-bin-hadoop3" "$SPARK_HOME" \
      && chown -R airflow:root "$SPARK_HOME"; \
    fi

ENV PATH="${SPARK_HOME}/bin:${PATH}"

USER airflow

# Install Airflow providers (latest versions compatible with Airflow 3.x)
RUN set --; \
    if [ -n "$PIP_TRUSTED_HOST" ]; then set -- --trusted-host "$PIP_TRUSTED_HOST"; fi; \
    pip install --no-cache-dir --index-url "$PIP_INDEX_URL" "$@" \
      "apache-airflow==${AIRFLOW_VERSION}" \
      apache-airflow-providers-apache-spark==5.5.0 \
      apache-airflow-providers-postgres==5.14.0 \
      apache-airflow-providers-apache-kafka==1.8.0 \
      apache-airflow-providers-docker==3.14.0 \
      apache-airflow-providers-http==5.6.3 \
      pyspark==4.1.0

# Create directories
RUN mkdir -p /opt/airflow/dags /opt/airflow/logs /opt/airflow/config

WORKDIR /opt/airflow
