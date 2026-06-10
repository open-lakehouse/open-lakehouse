# MLflow tracking server image for ECS Fargate (open-lakehouse / terraform/mlflow-ecs).
#
# A thin layer over the official MLflow `-full` image (which bundles psycopg2 +
# boto3, so Postgres and S3 work out of the box) plus the AWS-specific entrypoint
# that handles SNI TLS, managed-Postgres provisioning, and S3 artifact proxying.
#
# psql 16 is pulled from PGDG (not the distro default 13): libpq < 14 does not
# send TLS SNI, and SNI-routed managed Postgres (Databricks Lakebase / Neon)
# rejects such connections with "Connection does not have SNI".
#
# Built for linux/arm64 to match the Fargate ARM64 runtime (see
# scripts/terraform/mlflow-ecr-push.sh). Build context is this directory.
FROM ghcr.io/mlflow/mlflow:v3.13.0-full

USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates gnupg curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsS https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    . /etc/os-release; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-16; \
    apt-get purge -y --auto-remove gnupg curl; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/mlflow-entrypoint.sh
RUN chmod +x /usr/local/bin/mlflow-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mlflow-entrypoint.sh"]
