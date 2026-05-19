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
| Iceberg writes fail with "S3 access denied" | Check `.env` `S3_ACCESS_KEY`/`S3_SECRET_KEY` vs `config/unity-catalog/server.properties` | UC OSS credential vending mismatch. Both must reference the same SeaweedFS keys. |
| `unity-catalog` container restarts in a loop | `docker logs unity-catalog \| tail -100` | Most common: PostgreSQL not reachable. UC OSS uses Postgres as its metastore. Ensure `5432` is up. |
| Airflow webserver returns 502 | `docker logs airflow-webserver \| tail -50` and `docker logs airflow-scheduler` | Often: Postgres unreachable, or the airflow-init container failed. Re-run `./lakehouse start airflow`. |
| MLflow UI loads but no runs appear | `docker logs mlflow` | MLflow tracking URI mismatch — verify `MLFLOW_TRACKING_URI=http://localhost:5000` in your job. |
| `docker compose up` hangs at "Pulling …" | Network. | Check `docker pull alpine:latest` to confirm registry connectivity. |
| Spark job OOMs on first run | `docker stats spark-worker-41` while job runs | Bump `spark.driver.memory` / `spark.executor.memory` in `config/spark/spark-defaults.conf`. Defaults are 4g/8g — fine for demos, light for production. |
| `lakehouse status` shows "Spark master not running" but `docker ps` shows it | Container name mismatch — must be `spark-master-41` | Did you start with the right compose file? `docker-compose-spark41.yml` is the only valid one. |
| Kafka producer fails with "Topic does not exist" | `docker exec kafka kafka-topics --list --bootstrap-server localhost:9092` | Auto-topic-creation is on by default; if disabled, create explicitly via `kafka-topics --create`. |
| Unity Catalog returns 401 | `curl -v http://localhost:8081/api/2.1/unity-catalog/catalogs` | UC OSS 0.4.x runs without auth by default for local. If a token is being sent, your client is misconfigured. |
| Delta tables aren't visible via UC REST | Expected — UC OSS 0.4.x Iceberg REST endpoint surfaces Iceberg only | Use UC's Delta-native API path, or use UniForm which projects Delta as Iceberg. |

## When all else fails

```bash
# Capture full stack state
./lakehouse status --json > /tmp/lh-status.json
docker ps -a > /tmp/lh-docker.txt
for c in spark-master-41 spark-worker-41 kafka zookeeper unity-catalog mlflow airflow-webserver airflow-scheduler postgres; do
  docker logs --tail 200 "$c" > "/tmp/lh-$c.log" 2>&1
done
```

Hand these to the user. They have more context (laptop spec, recent changes) than you do for ambiguous failures.

## What NOT to do

- **Don't run `docker system prune -a`** to "clean up." It also nukes images you'd then have to redownload (~5GB).
- **Don't comment out failing tests** to make them green.
- **Don't bypass `./lakehouse preflight`** by editing the script.
- **Don't downgrade JAR versions** without confirming with the user. AWS SDK v2 is pinned to 2.24.6 for a Hadoop 3.4.1 compatibility reason.
