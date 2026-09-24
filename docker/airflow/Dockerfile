# Airflow 3.1.6 with Python 3.12
FROM apache/airflow:3.1.6-python3.12

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ARG SPARK_DIST_URL=https://archive.apache.org/dist/spark/spark-4.1.0/spark-4.1.0-bin-hadoop3.tgz

USER root

# Install system dependencies. Debian 11 "bullseye" LTS ended 2026-08-31, so the
# base image's apt sources (deb.debian.org) now 404 on the postgresql-13 / libpq5
# pool files. Repoint to archive.debian.org + skip Valid-Until so apt can still
# fetch. Long-term fix is a base-image bump off bullseye — tracked separately.
RUN rm -rf /var/lib/apt/lists/* \
    && sed -i -E 's|https?://deb.debian.org/debian-security|http://archive.debian.org/debian-security|g; s|https?://deb.debian.org/debian|http://archive.debian.org/debian|g; s|https?://security.debian.org|http://archive.debian.org/debian-security|g' /etc/apt/sources.list \
    && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid-until \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    openjdk-17-jre-headless \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME for Spark (Java 17 works with Spark 4.0 and 4.1)
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Download and install Spark (for spark-submit)
ENV SPARK_VERSION=4.1.0
ENV SPARK_HOME=/opt/spark
RUN curl -fsSL "$SPARK_DIST_URL" \
    | tar -xz -C /opt/ \
    && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 ${SPARK_HOME} \
    && chown -R airflow:root ${SPARK_HOME}

ENV PATH="${SPARK_HOME}/bin:${PATH}"

USER airflow

# Install Airflow providers (latest versions compatible with Airflow 3.x)
RUN set --; \
    if [ -n "$PIP_TRUSTED_HOST" ]; then set -- --trusted-host "$PIP_TRUSTED_HOST"; fi; \
    pip install --no-cache-dir --index-url "$PIP_INDEX_URL" "$@" \
      apache-airflow-providers-apache-spark==5.5.0 \
      apache-airflow-providers-postgres==5.14.0 \
      apache-airflow-providers-apache-kafka==1.8.0 \
      apache-airflow-providers-docker==3.14.0 \
      apache-airflow-providers-http==5.6.3 \
      pyspark==4.1.0

# Create directories
RUN mkdir -p /opt/airflow/dags /opt/airflow/logs /opt/airflow/config

WORKDIR /opt/airflow
