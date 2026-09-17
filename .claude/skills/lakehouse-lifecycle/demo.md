# Demo runbook

Goal: run one demo from `demos/<name>/` reliably, then tear down anything the demo created.

## Demo contract

Every demo under `demos/<name>/` is required to ship a `README.md` matching the template in `demos/_template/README.md`. The template has five fixed sections:

1. **Purpose** — one sentence, what the demo shows.
2. **Prereqs** — which services must be running (Spark, Kafka, UC, MLflow, Airflow).
3. **Run** — exact commands in order. Each command's expected stdout snippet.
4. **Expected output** — what success looks like (tables created, metrics logged, DAG run id, etc.).
5. **Teardown** — exact commands to remove demo artifacts (drop tables, delete Kafka topics, etc.). Or path to `teardown.sh`.

If a `demos/<name>/` directory exists but its `README.md` does not match this contract, treat it as broken — flag to the user, don't guess the run command.

## Running a demo

```bash
# 1. confirm prereqs are up
./lakehouse status --json | jq .all_healthy   # must be true

# 2. read the demo's README
cat demos/<name>/README.md

# 3. follow Run section commands in order
# 4. compare stdout against Expected output
# 5. run Teardown commands (or bash demos/<name>/teardown.sh)
```

## Reset / backup / restore around a demo

The teardown in a demo's `teardown.sh` removes only what that demo created (its S3
prefix, its tables/topics). To wipe the **whole** environment between demos, or to
protect state you care about, use the lifecycle commands rather than `docker compose
down -v` (which — since storage is Composed, PR #13 — now wipes `postgres-data`,
`seaweedfs-data`, and `uc-data` wholesale: every database, all object data, and the UC
catalog, in one unconfirmed step — see [stop.md](stop.md)):

```bash
# Snapshot everything first if the state matters (pg_dump per DB + S3 + volumes + UC H2).
./lakehouse backup                         # prints the artifact path + a restore command
./lakehouse restore --from <path>          # fail-stop and recoverable

# Start fresh (confirms; add --yes to skip the prompt, --dry-run to preview).
./lakehouse reset --all                    # databases + object store
./lakehouse reset --data                   # object store + dangling catalog/tracking rows only
./lakehouse reset --metadata --keep-mlflow # reset catalogs but preserve MLflow

# Confirm the result is consistent (four orphan classes; also flags interrupted resets).
./lakehouse doctor
```

Rule of thumb: **demo teardown = its own artifacts; `reset` = the whole world.**

## Discovery

```bash
ls demos/                       # demo directories
cat demos/README.md             # human-readable index
```

The currently-shipped placeholder demos are:

| Demo | Transport | Purpose (sketch) |
|------|-----------|------------------|
| `sdp-medallion` | `spark-pipelines` (Connect-backed) | Bronze → Silver → Gold via Spark Declarative Pipelines |
| `unity-catalog-multi-engine` | Spark Connect + DuckDB | UC OSS as a single catalog for Spark and DuckDB |
| `realtime-mode` | Spark Connect (Structured Streaming) | Kafka → Iceberg streaming with watermarked dedup |
| `local-mode-spark` | Local (no cluster) — **not yet implemented** | In-process Spark for laptop demos (placeholder for `--spark-local`) |

All but `local-mode-spark` are `.gitkeep` placeholders in this commit — content arrives demo-by-demo. The local-mode demo ships a README explaining the deferred state.

## When a demo doesn't exist yet

If the user asks you to run a demo whose directory is empty:
1. Don't fabricate the demo.
2. Offer to scaffold it from `demos/_template/`:
   ```bash
   cp -r demos/_template demos/<new-name>
   ```
3. Then build the demo with the user, following the template sections.

## Common cross-demo helpers

```bash
# Generate test data
./lakehouse testdata generate --days 7
./lakehouse testdata stream --speed 60     # backgrounds a producer

# Open Spark SQL shell against the cluster
docker exec -it spark-master-41 /opt/spark/bin/spark-sql

# Browse an Iceberg table
./lakehouse browsedata iceberg.bronze.orders

# Hit Unity Catalog REST directly
curl -s http://localhost:8081/api/2.1/unity-catalog/catalogs | jq .
```
