# Troubleshooting decision tree

Match the user-reported symptom to a row, then run the diagnostic. If diagnostic is inconclusive, escalate (read logs, ask the user). **Do not bypass safety checks** — if a service refuses to start because of a missing credential, fix the credential, don't comment out the check.

## Symptom → diagnostic → likely fix

| Symptom | Diagnostic | Likely fix |
|---------|-----------|------------|
| `lakehouse start all` exits before Docker logs | `./lakehouse preflight` | A port is held by a foreign process. `lsof -i :<port>` to find it. |
| Spark master starts but `lakehouse test` says "Spark not responding" | `docker logs spark-master-41 \| tail -50` | Usually a JAR mismatch. Re-run `./lakehouse setup` to re-verify JARs. |
| `spark-connect-41` keeps restarting | `docker logs spark-connect-41 \| tail -100` | Most common: master URL unreachable (race vs. master start). The compose has `depends_on` + `sleep 10` but on slow hardware bump the sleep. Second most common: `--packages` download failed — pre-warm by running `docker exec spark-connect-41 ls /root/.ivy2/cache/`. |
| Client gets `UNAVAILABLE: io exception` from `sc://localhost:15002` | `nc -z localhost 15002` then `docker ps \| grep connect` | Connect server isn't listening. Check container is up and not crash-looping. |
| SDP pipeline fails with `NoClassDefFoundError: SparkConnectGraphElementRegistry` | n/a | The cluster's Spark version doesn't include Connect, or the Connect server didn't start. SDP requires Connect — verify `./lakehouse status --json \| jq .spark.connect_grpc_listening` is true before running `spark-pipelines`. |
| `./lakehouse --spark-local <anything>` exits with not-implemented | Read the message | This is intentional. Local mode is roadmap, not built. Drop the flag (Connect is the default). |
| Delta writes to `unity.*` fail with "S3 access denied" | Check `.env` `S3_ACCESS_KEY`/`S3_SECRET_KEY` vs `config/unity-catalog/server.properties` | UC OSS credential-vending mismatch. Both must reference the same SeaweedFS keys. (Writes are Delta via `unity.`; the `iceberg.` catalog is read-only.) |
| `unity-catalog` container restarts in a loop | `docker logs unity-catalog \| tail -100` | UC OSS runs on **embedded H2** in this stack (`uc-data` is unmounted — it is NOT Postgres-backed). A loop is usually a bad `server.properties` (e.g. an uncommented PostgreSQL block pointing nowhere) or a bind-mount path error, not a Postgres outage. |
| `unity-catalog` shows "unhealthy" but the API answers | `docker inspect --format '{{.State.Health.Status}}' unity-catalog` | The image ships busybox `wget`, not `curl`; the healthcheck uses `wget`. If you still see `unhealthy` on an old container, recreate it (`./lakehouse stop unity-catalog && ./lakehouse start unity-catalog`) to pick up the fixed healthcheck. |
| Airflow webserver returns 502 | `docker logs airflow-webserver \| tail -50` and `docker logs airflow-scheduler` | Often: Postgres unreachable, or the airflow-init container failed. Re-run `./lakehouse start airflow`. |
| MLflow UI loads but no runs appear | `docker logs mlflow-server` | MLflow tracking URI mismatch — verify `MLFLOW_TRACKING_URI=http://localhost:5000` in your job. |
| `status` reports `mlflow: false` while the UI works | `docker ps \| grep mlflow` | The Compose container is `mlflow-server`, not `mlflow`; the CLI resolves this. If a doc or script still probes `mlflow`, fix the name. |
| "start fresh" leaves a broken/inconsistent stack | `./lakehouse doctor` | Never use `docker compose down -v` to reset (since storage is Composed, PR #13, `-v` now wipes `postgres-data` + `seaweedfs-data` + `uc-data` — every database, all object data, and the UC catalog — see [stop.md](stop.md)). Use `./lakehouse reset --all` (or `--data`/`--metadata`); back up first with `./lakehouse backup` if state matters. `doctor` reports orphans + any interrupted reset/restore. |
| `docker compose up` hangs at "Pulling …" | Network. | Check `docker pull alpine:latest` to confirm registry connectivity. |
| Spark job OOMs on first run | `docker stats spark-worker-41` while job runs | Bump `spark.driver.memory` / `spark.executor.memory` in `config/spark/spark-defaults.conf`. Defaults are 4g/8g — fine for demos, light for production. |
| `lakehouse status` shows "Spark master not running" but `docker ps` shows it | Container name mismatch — must be `spark-master-41` | Did you start with the right compose file? `docker-compose-spark41.yml` is the only valid one. |
| Kafka producer fails with "Topic does not exist" | `docker exec kafka kafka-topics --list --bootstrap-server localhost:9092` | Auto-topic-creation is on by default; if disabled, create explicitly via `kafka-topics --create`. |
| Unity Catalog returns 401 | `curl -v http://localhost:8081/api/2.1/unity-catalog/catalogs` | UC OSS 0.5.0 runs without auth by default for local. If a token is being sent, your client is misconfigured. |
| Delta tables aren't visible via the UC **Iceberg** REST endpoint | Expected — that endpoint surfaces Iceberg only | Delta tables live under UC's native `/tables` API (catalog `unity.*`); read them via Spark. UniForm (Delta→Iceberg-readable metadata) is an untested avenue here, not a supported path. |

## When all else fails

```bash
# Capture full stack state
./lakehouse status --json > /tmp/lh-status.json
docker ps -a > /tmp/lh-docker.txt
for c in spark-master-41 spark-worker-41 kafka zookeeper unity-catalog mlflow-server airflow-webserver airflow-scheduler; do
  docker logs --tail 200 "$c" > "/tmp/lh-$c.log" 2>&1
done
```

Hand these to the user. They have more context (laptop spec, recent changes) than you do for ambiguous failures.

## What NOT to do

- **Don't run `docker system prune -a`** to "clean up." It also nukes images you'd then have to redownload (~5GB).
- **Don't comment out failing tests** to make them green.
- **Don't bypass `./lakehouse preflight`** by editing the script.
- **Don't downgrade JAR versions** without confirming with the user. AWS SDK v2 is pinned to 2.24.6 for a Hadoop 3.4.1 compatibility reason.
