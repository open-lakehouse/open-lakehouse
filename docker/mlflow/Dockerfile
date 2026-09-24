# MLflow tracking server + AI Gateway (local stack).
#
# The `-full` image variant bundles psycopg2-binary + boto3, so Postgres and S3
# work out of the box. We add the postgresql-client (psql) CLI because the
# entrypoint uses it to auto-provision the MLflow role + db against the local
# Postgres container.
#
# The AWS deploy uses a separate image under terraform/mlflow-ecs/docker (psql 16
# for SNI + the AWS entrypoint). Keep this one simple.
FROM ghcr.io/mlflow/mlflow:v3.14.0-full

USER root

# Debian 11 "bullseye" LTS ended 2026-08-31, so this base image's apt sources
# (deb.debian.org/{debian,debian-security}) now 404 on the postgresql-13 /
# libpq5 pool files. Repoint to archive.debian.org and skip Valid-Until (the
# archived Release files are "expired") so apt can still fetch postgresql-client.
# Long-term fix is a base-image bump off bullseye — tracked separately.
RUN rm -rf /var/lib/apt/lists/* \
    && sed -i -E 's|https?://deb.debian.org/debian-security|http://archive.debian.org/debian-security|g; s|https?://deb.debian.org/debian|http://archive.debian.org/debian|g; s|https?://security.debian.org|http://archive.debian.org/debian-security|g' /etc/apt/sources.list \
    && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid-until \
    && apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY docker/mlflow/entrypoint.sh /usr/local/bin/mlflow-entrypoint.sh
RUN chmod +x /usr/local/bin/mlflow-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mlflow-entrypoint.sh"]
