# Stop runbook

Goal: bring everything down cleanly without data loss.

## Default — quick stop (preserves state)

```bash
./lakehouse stop all            # Spark + Kafka
./lakehouse stop unity-catalog
./lakehouse stop airflow
./lakehouse stop mlflow
```

This runs `docker compose down` for each compose file. Containers are removed; **named volumes are preserved**, so Unity Catalog metadata, MLflow runs, and Airflow DAG history survive the restart.

To restart later, follow [start.md](start.md) from Step 3.

## Full teardown — destructive (wipes everything)

Use only when the user explicitly asks to "reset", "clean up", or "start fresh", and you have confirmed they accept data loss.

```bash
docker compose -f docker-compose-spark41.yml      down -v
docker compose -f docker-compose-kafka.yml        down -v
docker compose -f docker-compose-unity-catalog.yml down -v
docker compose -f docker-compose-airflow.yml      down -v
docker compose -f docker-compose-mlflow.yml       down -v
```

`-v` removes named volumes. **All Unity Catalog tables, MLflow tracking history, and Airflow DAG state are deleted.** This does NOT touch:
- SeaweedFS object data (lives in PostgreSQL-backed S3 store, separate)
- The Iceberg/Delta files in S3 (orphaned but recoverable if you bring UC back with the same warehouse path)
- The local PostgreSQL instance on host port 5432

For a truly clean slate including SeaweedFS data:

```bash
docker volume ls | grep seaweedfs
docker volume rm <listed_volumes>
```

## Verifying nothing is left running

```bash
docker ps --filter "name=spark-\|name=kafka\|name=zookeeper\|name=unity-catalog\|name=airflow\|name=mlflow"
```

Should return an empty list.

## Restart vs stop+start

For config changes that need a fresh container:

```bash
./lakehouse restart spark   # equivalent to stop + 2s sleep + start
```

For Java heap or JAR changes, prefer full stop + start (`restart` reuses the same compose project state).
