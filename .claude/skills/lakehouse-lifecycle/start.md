# Start runbook

Goal: bring the open-lakehouse stack from cold (nothing running) to healthy. Execute steps in order. **Do not skip preflight.** If a step exits non-zero, jump to the matching failure branch — do not just retry.

## Step 0 — sanity (10s)

```bash
cd ~/open-lakehouse        # or wherever the repo lives
docker info > /dev/null    # Docker daemon must be reachable
test -x ./lakehouse        # CLI must be executable
```

If Docker is not reachable: ask the user to start Docker Desktop / `systemctl start docker`. Do not proceed.

## Step 1 — private credentials, storage and config

```bash
./lakehouse setup --credentials-only
./lakehouse start storage
./lakehouse setup
```

Expected: `Setup complete!` at the bottom. The first run will:
1. Generate missing local credentials in private `.env` (preserve existing values)
2. Align private Spark and Unity Catalog S3 credentials, then start Compose storage
3. Download ~860MB of JARs into `jars/` (idempotent — uses checksum verify)
4. `poetry install`
5. Probe disk space and port conflicts

**Failure branch — credential recovery**: setup identifies a missing persistent key or conflicting S3 configuration. Restore the original value from a private backup and re-run; do not rotate credentials or remove volumes to bypass the error. See [automatic local credentials](../../../docs/guides/local-credentials.md). Explicit environment files and overlays bypass the local bootstrap.

**Failure branch — JAR download fails**: typically transient network. Re-run `./lakehouse setup`. If three retries fail, run `bash scripts/tools/download-jars.sh` directly and read the error.

## Step 2 — preflight (5s)

```bash
./lakehouse preflight
```

Expected: `All preflight checks passed`. This verifies PostgreSQL is reachable, SeaweedFS is reachable (if you intend to use S3 storage outside of Docker), and no port conflicts exist on 5432, 8333, 9092, 2181, 7078, 8081, 8082, 8085, 5000, 5001.

**Failure branch — port already in use**: read which port. If it's our container from a previous run (`docker ps`), preflight already accepts it. If it's a foreign process, ask the user to free the port before continuing.

## Step 3 — start services (first builds can take several minutes)

```bash
./lakehouse start all          # complete stack, including Airflow, notebooks and dashboard
```

`start all` starts storage, Spark, Kafka, Unity Catalog, MLflow, Airflow, notebooks,
Delta Sharing and dashboard in dependency order. Use `./lakehouse start core` for
storage, Spark and Kafka only, then start any other services individually. Both
groups include the **Spark Connect server** (container `spark-connect-41`, gRPC
on port 15002) alongside the master and worker. First start pulls `spark-connect_2.13:4.1.0` from Maven on the connect container — that adds ~30s. Subsequent starts hit the local Ivy cache.

A failed start/readiness check stops the group; inspect the reported service and
retry after correcting it. Earlier services remain running. Startup does not
seed demo tables or enable dashboard code execution.


The CLI exports `LAKEHOUSE_SPARK_REMOTE=sc://localhost:15002` and `LAKEHOUSE_SPARK_MODE=connect`. Demos should read these instead of hardcoding the endpoint.

## Step 4 — verify (15s)

```bash
./lakehouse status --json | jq .all_healthy
```

Expected: `true`. The healthcheck now requires `spark.connect_grpc_listening: true` in addition to master/PostgreSQL/SeaweedFS — if `all_healthy` is false, check the JSON for which one's red. Spark Connect takes the longest to come up; if it's the only failure, give it another 30s.

```bash
./lakehouse test
```

Expected: `All tests passed!`. This runs connectivity tests against every started service.

## Step 5 — smoke (30s, optional)

```bash
bash .claude/skills/lakehouse-lifecycle/scripts/smoke.sh
```

Writes one row to `iceberg.bronze._smoke`, reads it back, drops the table. If this passes, the catalog + S3 + Spark loop is wired correctly end-to-end.

## What "started" looks like

A healthy `./lakehouse status` shows green checks for: PostgreSQL, SeaweedFS, Unity Catalog REST, `spark-master-41`, `spark-worker-41`, `spark-connect-41` (gRPC listening on 15002), `kafka`, `zookeeper`, Airflow, MLflow, Delta Sharing and dashboard after a complete start. Jupyter is
checked during startup and can also be opened on port 8889.

## After start

You can now run any demo: see [demo.md](demo.md). Stop the stack with [stop.md](stop.md) when done.
