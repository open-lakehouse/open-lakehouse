# MLflow tracking server + AI Gateway (local stack).
#
# The `-full` image variant bundles psycopg2-binary + boto3, so Postgres and S3
# work out of the box. We add the postgresql-client (psql) CLI because the
# entrypoint uses it to auto-provision the MLflow role + db against the local
# Postgres container.
#
# The AWS deploy uses a separate image under terraform/mlflow-ecs/docker (psql 16
# for SNI + the AWS entrypoint). Keep this one simple.
FROM ghcr.io/mlflow/mlflow:v3.13.0-full

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY docker/mlflow/entrypoint.sh /usr/local/bin/mlflow-entrypoint.sh
RUN chmod +x /usr/local/bin/mlflow-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mlflow-entrypoint.sh"]
