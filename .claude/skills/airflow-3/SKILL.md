---
name: airflow-3
description: Apache Airflow 3.1 orchestration for this stack. Load when writing DAGs, dealing with the 2→3 migration gotchas, configuring Spark/Kafka connections, or debugging Airflow inside the docker-compose-airflow.yml setup.
---

# Airflow 3.1

This stack runs Airflow 3.1.6 via `docker-compose-airflow.yml`. UI is on `http://localhost:8085` (default admin/admin — change in `.env` for any non-local use). Containers: `airflow-webserver`, `airflow-scheduler`, `airflow-triggerer`, plus a one-shot `airflow-init`.

DAGs live in `dags/`. The directory is mounted into all Airflow containers; new files appear in the UI within ~30s.

## 3.x breaking changes that bite

Airflow 3 changes a lot from 2.x. The ones you'll hit:

1. **`schedule_interval` is gone.** Use `schedule=` (a cron string, timedelta, dataset, or `None`).
2. **TaskFlow is the default API.** Old `PythonOperator(python_callable=...)` still works but new DAGs should use `@task`.
3. **`DAG` import path changed** — `from airflow.sdk import DAG, task` (new SDK split). The legacy `from airflow import DAG` still works in 3.1 but is deprecated.
4. **Datasets renamed to `Asset`** in 3.x. Use `from airflow.sdk import Asset`.
5. **`start_date` is required** and must be in the past for the DAG to run.
6. **Provider packages are no longer in core.** Spark, Postgres, Kafka providers are installed via the Airflow Dockerfile (`docker/airflow/Dockerfile`).

## Minimal DAG template (Airflow 3 style)

```python
from datetime import datetime, timedelta
from airflow.sdk import DAG, task

with DAG(
    dag_id="hello_lakehouse",
    start_date=datetime(2026, 1, 1),
    schedule=timedelta(hours=1),
    catchup=False,
    tags=["demo"],
):
    @task
    def extract():
        return {"rows": 42}

    @task
    def transform(payload: dict) -> dict:
        return {"rows": payload["rows"] * 2}

    @task
    def load(payload: dict):
        print(f"loaded {payload['rows']} rows")

    load(transform(extract()))
```

## Triggering Spark jobs

Two common patterns:

### Bash + docker exec (simplest)

```python
from airflow.providers.standard.operators.bash import BashOperator

run_pipeline = BashOperator(
    task_id="run_pipeline",
    bash_command="docker exec spark-master-41 /opt/spark/bin/spark-submit /scripts/pipelines/pipeline_sdp.py",
)
```

This requires the Airflow worker to have Docker socket access. The compose file mounts `/var/run/docker.sock` for this reason. Fine for local; for AWS deployment, use SparkSubmitOperator or run Spark as a separate service.

### SparkSubmitOperator

```python
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

submit = SparkSubmitOperator(
    task_id="submit",
    application="/scripts/pipelines/pipeline_sdp.py",
    conn_id="spark_local",     # configured in Airflow UI or via env var AIRFLOW_CONN_SPARK_LOCAL
    conf={"spark.executor.memory": "4g"},
)
```

You need the spark-submit binary in the Airflow container — `docker/airflow/Dockerfile` installs it.

## Connections

Pre-configured connections (see `config/airflow/setup_connections.sh`):

| conn_id | Type | URL |
|---------|------|-----|
| `spark_local` | spark | `spark://spark-master-41:7078` |
| `postgres_default` | postgres | `postgresql://...` (system PG) |
| `kafka_default` | kafka | `kafka:9092` |

Set or override via `AIRFLOW_CONN_*` env vars in `.env`.

## DAG patterns for this stack

- **Iceberg maintenance** — daily compaction + snapshot expiration. SQL via `spark-submit`.
- **Streaming pipeline lifecycle** — DAG isn't the right tool for a 24/7 stream. Instead use a DAG to start/stop the stream container at scheduled times, or for sensor patterns.
- **Backfill** — `catchup=True` + `start_date` in the past + explicit `dagrun_timeout`. Watch out: Airflow 3 can spawn many catchup runs at once; set `max_active_runs=1`.

## Debugging

```bash
docker logs airflow-scheduler --tail 100      # task scheduling, retries, deferrals
docker logs airflow-webserver --tail 50       # UI / API errors
docker logs airflow-triggerer --tail 50       # deferred operators (sensors that yield)
```

Inside the scheduler container:

```bash
docker exec -it airflow-scheduler airflow dags list
docker exec -it airflow-scheduler airflow tasks list <dag_id>
docker exec -it airflow-scheduler airflow dags test <dag_id> $(date +%Y-%m-%d)
```

`airflow dags test` runs a DAG in-process without scheduling — fastest way to validate.

## Common errors

- **`DAG import error: ModuleNotFoundError`** — the import is from a provider not installed. Add the provider to `docker/airflow/Dockerfile`'s `pip install` line and rebuild (`./lakehouse start airflow --rebuild`).
- **`start_date in the future`** — DAG won't run until that date. Move `start_date` to a past date and clear the DAG state.
- **Task stuck in `queued`** — scheduler can't allocate it. Check `airflow-scheduler` logs for "no available workers" — usually means the worker container crashed.
- **`Database is locked` (SQLite)** — Airflow 3.1 defaults to PostgreSQL in our compose. If you see SQLite errors, something overrode the metadata URL — check `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`.
