#!/usr/bin/env bash
# MLflow ECS entrypoint (open-lakehouse / terraform/mlflow-ecs).
#
# Extends the simple local entrypoint with the knobs needed to run against
# managed Postgres behind an ALB on AWS:
#   - MLFLOW_PG_SSLMODE        TLS mode appended to the backend URI + exported as
#                              PGSSLMODE so psql honors it (Lakebase requires SSL).
#   - MLFLOW_SKIP_PROVISION    skip role/db provisioning for managed Postgres.
#   - POSTGRES_ADMIN_DB        maintenance db for CREATE DATABASE (Lakebase uses
#                              "databricks_postgres", not "postgres").
#   - MLFLOW_ARTIFACT_ROOT_FLAG / MLFLOW_ARTIFACTS_DESTINATION  proxy artifacts to S3.
#   - MLFLOW_EXTRA_ARGS        e.g. --allowed-hosts / --cors-allowed-origins.
#
# Safe to re-run; all DDL is guarded.
set -euo pipefail

PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_SUPERUSER="${POSTGRES_USER:-postgres}"
PG_SUPERPASS="${POSTGRES_PASSWORD:-}"
# Maintenance database the privileged role connects to in order to CREATE ROLE /
# CREATE DATABASE. Vanilla Postgres exposes "postgres"; Databricks Lakebase uses
# "databricks_postgres". Only used on the provisioning path.
PG_ADMIN_DB="${POSTGRES_ADMIN_DB:-postgres}"

MLFLOW_PG_USER="${MLFLOW_PG_USER:-mlflow}"
MLFLOW_PG_PASS="${MLFLOW_PG_PASS:-mlflow_password}"
MLFLOW_PG_DB="${MLFLOW_PG_DB:-mlflow}"

# TLS mode for every Postgres connection (psql + the SQLAlchemy backend store).
# Empty for the local stack; set to "require" for managed Postgres that mandates
# SSL, such as Databricks Lakebase. Exporting PGSSLMODE makes libpq (psql) honor
# it; it is also appended to the backend-store-uri below.
MLFLOW_PG_SSLMODE="${MLFLOW_PG_SSLMODE:-}"
[[ -n "${MLFLOW_PG_SSLMODE}" ]] && export PGSSLMODE="${MLFLOW_PG_SSLMODE}"

# When 1, skip role/db auto-provisioning entirely. Use for managed / external
# Postgres (e.g. Lakebase) where the role and database already exist and there
# is no reachable superuser. The entrypoint just waits until MLflow can connect
# with its own credentials, then starts the server.
MLFLOW_SKIP_PROVISION="${MLFLOW_SKIP_PROVISION:-0}"

if [[ "${MLFLOW_SKIP_PROVISION}" == "1" ]]; then
    echo "[mlflow-entrypoint] provisioning disabled; waiting for ${MLFLOW_PG_USER}@${PG_HOST}:${PG_PORT}/${MLFLOW_PG_DB}..."
    for _ in $(seq 1 30); do
        if PGPASSWORD="${MLFLOW_PG_PASS}" psql \
             -h "${PG_HOST}" -p "${PG_PORT}" -U "${MLFLOW_PG_USER}" -d "${MLFLOW_PG_DB}" \
             -c 'SELECT 1' >/dev/null 2>&1; then
            echo "[mlflow-entrypoint] connected as '${MLFLOW_PG_USER}' to db '${MLFLOW_PG_DB}'"
            break
        fi
        sleep 1
    done
else
    echo "[mlflow-entrypoint] waiting for postgres at ${PG_HOST}:${PG_PORT}..."
    for _ in $(seq 1 30); do
        if PGPASSWORD="${PG_SUPERPASS}" psql \
             -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_SUPERUSER}" -d "${PG_ADMIN_DB}" \
             -c 'SELECT 1' >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # Fast path: if mlflow can already connect with its own credentials, skip
    # provisioning entirely. This covers the common case where a user has set
    # up the role and db once (manually or via ./lakehouse setup-mlflow).
    if PGPASSWORD="${MLFLOW_PG_PASS}" psql \
         -h "${PG_HOST}" -p "${PG_PORT}" -U "${MLFLOW_PG_USER}" -d "${MLFLOW_PG_DB}" \
         -c 'SELECT 1' >/dev/null 2>&1; then
        echo "[mlflow-entrypoint] role '${MLFLOW_PG_USER}' and db '${MLFLOW_PG_DB}' already present"
    else
        echo "[mlflow-entrypoint] attempting to provision role '${MLFLOW_PG_USER}' and db '${MLFLOW_PG_DB}'..."
        prov_ok=1
        PGPASSWORD="${PG_SUPERPASS}" psql \
            -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_SUPERUSER}" -d "${PG_ADMIN_DB}" \
            -v ON_ERROR_STOP=1 <<SQL || prov_ok=0
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${MLFLOW_PG_USER}') THEN
        CREATE ROLE "${MLFLOW_PG_USER}" WITH LOGIN PASSWORD '${MLFLOW_PG_PASS}';
    END IF;
END
\$\$;
SQL

        if [[ "${prov_ok}" == "1" ]] && ! PGPASSWORD="${PG_SUPERPASS}" psql \
               -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_SUPERUSER}" -d "${PG_ADMIN_DB}" \
               -tAc "SELECT 1 FROM pg_database WHERE datname='${MLFLOW_PG_DB}'" 2>/dev/null | grep -q 1; then
            PGPASSWORD="${PG_SUPERPASS}" psql \
                -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_SUPERUSER}" -d "${PG_ADMIN_DB}" \
                -v ON_ERROR_STOP=1 \
                -c "CREATE DATABASE \"${MLFLOW_PG_DB}\" OWNER \"${MLFLOW_PG_USER}\";" || prov_ok=0
        fi

        if [[ "${prov_ok}" == "0" ]]; then
            cat >&2 <<EOF
[mlflow-entrypoint] unable to auto-provision MLflow role/db.
POSTGRES_USER='${PG_SUPERUSER}' lacks CREATEROLE/CREATEDB on '${PG_ADMIN_DB}', or
the db is unreachable. Provision once from a privileged session and restart, or
set MLFLOW_SKIP_PROVISION=1 if the role/db already exist (e.g. managed Postgres):

    psql -U <privileged-role> -d ${PG_ADMIN_DB} <<'SQL'
    CREATE ROLE "${MLFLOW_PG_USER}" WITH LOGIN PASSWORD '<password>';
    CREATE DATABASE "${MLFLOW_PG_DB}" OWNER "${MLFLOW_PG_USER}";
    SQL

EOF
            exit 1
        fi
    fi
fi

# Artifact handling. MLFLOW_ARTIFACT_ROOT_FLAG selects how the artifact store is
# wired:
#   --default-artifact-root  (default) new experiments get this URI and clients
#                            read/write the store directly (needs creds). This
#                            is the local SeaweedFS behavior.
#   --artifacts-destination  the tracking server proxies artifact I/O to this
#                            URI (serve-artifacts is on by default), so remote
#                            clients never need storage credentials. Use this
#                            behind an ALB on AWS where the task role grants S3.
MLFLOW_ARTIFACT_ROOT_FLAG="${MLFLOW_ARTIFACT_ROOT_FLAG:---default-artifact-root}"
MLFLOW_ARTIFACTS_DESTINATION="${MLFLOW_ARTIFACTS_DESTINATION:-s3://lakehouse/mlflow-artifacts}"

# Optional extra args appended verbatim (word-split) to the server command.
# Used to pass deployment-specific flags such as --allowed-hosts and
# --cors-allowed-origins when running behind a reverse proxy / ALB. Empty by
# default, so local behavior is unchanged.
read -r -a extra_args <<<"${MLFLOW_EXTRA_ARGS:-}"

# Backend store URI, with sslmode appended when a TLS mode is configured.
backend_store_uri="postgresql://${MLFLOW_PG_USER}:${MLFLOW_PG_PASS}@${PG_HOST}:${PG_PORT}/${MLFLOW_PG_DB}"
if [[ -n "${MLFLOW_PG_SSLMODE}" ]]; then
    backend_store_uri="${backend_store_uri}?sslmode=${MLFLOW_PG_SSLMODE}"
fi

echo "[mlflow-entrypoint] starting mlflow server"
exec mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri "${backend_store_uri}" \
    "${MLFLOW_ARTIFACT_ROOT_FLAG}" "${MLFLOW_ARTIFACTS_DESTINATION}" \
    "${extra_args[@]}"
