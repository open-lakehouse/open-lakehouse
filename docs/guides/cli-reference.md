# CLI Reference

The `lakehouse` script is the single entrypoint for managing the stack. It dispatches `docker compose`, runs connectivity tests, applies migrations, and exposes a JSON status interface for automation.

## Usage

```bash
./lakehouse [--spark-connect|--spark-local] [--json] <command> [args]
```

## Global options

| Flag | Meaning |
|------|---------|
| `--spark-connect` | (Default) Use Spark Connect on `sc://localhost:15002`. Exports `LAKEHOUSE_SPARK_MODE=connect` and `LAKEHOUSE_SPARK_REMOTE=sc://localhost:15002`. |
| `--spark-local` | In-process Spark mode — **not yet implemented**. The flag exists for forward-compat; using it exits with a message and pointer to `demos/local-mode-spark/`. |
| `--json` | Emit machine-readable JSON (status command). |

There is **no Spark version flag**. open-lakehouse is Spark 4.1 only; the upstream `lakehouse-stack` repo handles multi-version setups.

Flags can appear before or after the command:

```bash
./lakehouse --spark-connect start all
./lakehouse status --json
```

## Commands

### `setup`

Validate environment, install Python deps via Poetry, download JARs (~860 MB into `jars/`, idempotent), and create the local PostgreSQL database.

```bash
./lakehouse setup
./lakehouse setup --credentials-only  # private credentials/configs only
```

Runs the following steps and reports each:

1. Check prerequisites (Docker, Poetry, psql, jq, nc, curl)
2. Prepare private credentials and recover existing values without rotating them
3. Align Spark and Unity Catalog S3 configuration; stop on conflicting values
4. Download/verify JARs
5. `poetry install --quiet`
6. Create local `iceberg_catalog` database if `psql` is available
7. Check disk space and port conflicts

`--credentials-only` requires Python and a reachable Docker daemon, then prepares
the private configuration without downloading dependencies or starting services.
See [credential recovery](local-credentials.md) before changing existing secrets.

### `start [service]`

Start one of the services or all of them.

```bash
./lakehouse start all              # complete stack, storage first and dashboard last
./lakehouse start core             # storage + Spark master/worker/Connect + Kafka/Zookeeper
./lakehouse start unity-catalog
./lakehouse start mlflow
./lakehouse start airflow
./lakehouse start spark            # Spark master + worker + Connect server
./lakehouse start kafka            # Kafka only
```

`all` (also the default for bare `start`) starts storage, Spark, Kafka, Unity Catalog,
MLflow, Airflow, notebooks, Delta Sharing and dashboard, in that order. `core`
starts storage, Spark and Kafka only. Individual service commands remain available,
including `start sharing` as an alias for `share start`. A failed build, startup or
readiness check stops the group and returns a failure; earlier services remain
running so the failure can be inspected and the command retried. Dashboard code
execution stays disabled unless explicitly configured.

Unity Catalog and MLflow HTTP readiness checks reject error responses. Delta
Sharing readiness checks its authenticated shares API before publishing the
client profile. Profile writes are atomic and owner-only; a failed write keeps
the previous profile and fails startup.

### `stop [service]`

Stop a service or group (preserves named volumes — data is safe). `all` and `core`
stop the same members they start, in reverse order with storage last. If a stop
fails, dependencies stay running. `stop core` includes storage; it does not stop
services outside the core group.

```bash
./lakehouse stop all
./lakehouse stop core
./lakehouse stop airflow
```

Use `./lakehouse reset --all --dry-run` to review a destructive reset; ordinary stop
and restart never delete named volumes.

### `restart [service]`

Equivalent to `stop` + 2s sleep + `start`, using the same service or group on both
sides. Use for config changes that need a fresh container.

### `status [--json]`

Human-readable or JSON status.

```bash
./lakehouse status
./lakehouse status --json | jq '.all_healthy'
```

JSON shape:

```json
{
  "mode": "connect",
  "services": {"postgresql": true, "seaweedfs": true, "unity_catalog": true, "mlflow": true},
  "spark": {
    "version": "4.1",
    "master": true,
    "worker": true,
    "connect_container": true,
    "connect_grpc_listening": true,
    "remote": "sc://localhost:15002"
  },
  "kafka": {"broker": true, "zookeeper": true},
  "airflow": {"webserver": true, "scheduler": true},
  "all_healthy": true
}
```

`all_healthy` requires `connect_grpc_listening` to be `true` — clients can't do anything useful without Connect.

### `test`

Connectivity tests against every started service. Returns non-zero exit code on any failure.

```bash
./lakehouse test
```

Probes: PostgreSQL, SeaweedFS, Kafka broker, Spark master, Unity Catalog REST + Iceberg endpoint, Airflow webserver.

### `preflight`

Run pre-start checks: port availability, PostgreSQL reachability, SeaweedFS reachability. Faster than `setup`; safe to run anytime.

```bash
./lakehouse preflight
```

### `check-config`

Validate `.env` and `config/spark/spark-defaults.conf` consistency. Catches placeholder values that didn't get filled in.

```bash
./lakehouse check-config
```

### `logs [service]`

Tail logs for a service:

```bash
./lakehouse logs spark-master
./lakehouse logs spark-worker
./lakehouse logs spark-connect
./lakehouse logs kafka
./lakehouse logs zookeeper
./lakehouse logs unity-catalog
./lakehouse logs mlflow
./lakehouse logs airflow-webserver
./lakehouse logs airflow-scheduler
./lakehouse logs airflow-triggerer
```

### `migrate [--dry-run]`

Apply SQL migrations from `schemas/` to the local PostgreSQL database. Migrations are tracked in a `_migrations` table.

```bash
./lakehouse migrate              # Apply pending migrations
./lakehouse migrate --dry-run    # Preview without applying
```

### `producer`

Start the demo Kafka producer (emits synthetic order events).

```bash
./lakehouse producer
```

### `consumer`

Run the Spark streaming consumer against Kafka — useful for verifying the stream → Iceberg path.

```bash
./lakehouse consumer
```

### `testdata <subcommand>`

Test-data generation utilities.

```bash
./lakehouse testdata generate --days 7         # Generate 7-day dataset
./lakehouse testdata stream --speed 60         # Stream to Kafka 60× wall-clock
./lakehouse testdata load                      # Load into Iceberg
./lakehouse testdata stats                     # Dataset summary
./lakehouse testdata clean                     # Remove generated files
```

### `browsedata [table]`

Open an interactive `spark-sql` view of an Iceberg table (default: `iceberg.bronze.orders`).

```bash
./lakehouse browsedata
./lakehouse browsedata iceberg.gold.hourly_metrics
```

## Examples

```bash
# Daily start
./lakehouse preflight && ./lakehouse start all && ./lakehouse status --json | jq .all_healthy

# Run a demo
./lakehouse start unity-catalog
cat demos/streaming-kafka-to-iceberg/README.md      # follow Run section

# Daily stop
./lakehouse stop all

# Preview a full reset before confirming it
./lakehouse reset --all --dry-run
```

## For AI agents

The CLI exits non-zero on failure and emits structured stdout. Pair with `./lakehouse status --json` for automation. Deterministic runbooks live at [`.claude/skills/lakehouse-lifecycle/`](../../.claude/skills/lakehouse-lifecycle/).
