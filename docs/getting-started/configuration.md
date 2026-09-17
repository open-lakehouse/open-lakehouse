# Configuration

This guide covers configuring the lakehouse stack for your environment.

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (credentials, endpoints) |
| `config/spark/spark-defaults.conf` | Spark and Iceberg settings |

## Environment Variables (.env)

Create from the template:
```bash
cp .env.example .env
```

### Required Variables

These values are consumed two ways: Docker Compose interpolates them into the
service definitions, and host-side tooling (`init-storage.sh`, `migrate`, the
`test` checks) reads them directly. The **hosts here are the published ports on
`localhost`** — that is the host-side view. In-container config never uses these
hosts; containers reach each other by service name (`postgres`, `seaweedfs`,
`unity-catalog`), which is already baked into the bind-mounted
`spark-defaults.conf` and the compose files.

```bash
# PostgreSQL (metastore for UC / MLflow / Airflow / iceberg_catalog)
POSTGRES_USER=lakehouse
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=localhost   # host-side view; containers use the `postgres` service name
POSTGRES_PORT=5432

# SeaweedFS (S3-compatible storage)
S3_ENDPOINT=http://localhost:8333   # host-side view; containers use http://seaweedfs:8333
S3_ACCESS_KEY=lakehouse_s3
S3_SECRET_KEY=lakehouse_s3_secret
S3_BUCKET=lakehouse
S3_WAREHOUSE=s3a://lakehouse/warehouse

# Iceberg warehouse (derived from above)
ICEBERG_WAREHOUSE=${S3_WAREHOUSE}
```

> **No JDBC catalog.** The Iceberg catalog is Unity Catalog OSS reached over REST
> (golden rule 1) — there is **no** `ICEBERG_CATALOG_URI` / `spark.sql.catalog.iceberg.type=jdbc`
> path. `iceberg_catalog` is just a PostgreSQL database name the init step creates;
> it is not a Spark catalog backend.

### Host vs. in-network addressing

Since PR #13, PostgreSQL and SeaweedFS are Compose services (see
`docker-compose-storage.yml`) on the shared `lakehouse-network` bridge, publishing
their ports to the host:

| Caller | PostgreSQL | S3 endpoint |
|--------|-----------|-------------|
| From another container (in-network) | `postgres:5432` | `http://seaweedfs:8333` |
| From your host (published ports) | `localhost:5432` | `http://localhost:8333` |

## Spark Configuration

Create from the template:
```bash
cp config/spark/spark-defaults.conf.example config/spark/spark-defaults.conf
```

### Key Settings

This config runs **inside** the Spark containers on the bridge network, so every
endpoint is an **in-network service name**, not `localhost`. (From your host you
would use `localhost:8081` / `localhost:8333`, but Spark reads this file from
inside a container.)

```properties
# unity — Unity Catalog OSS, Delta tables (PRIMARY write path)
spark.sql.catalog.unity=io.unitycatalog.spark.UCSingleCatalog
spark.sql.catalog.unity.uri=http://unity-catalog:8080
spark.sql.catalog.unity.token=not_used

# iceberg — UC OSS Iceberg REST endpoint, READ-ONLY (the only catalog mode here;
# there is no JDBC catalog — golden rule 1)
spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,io.delta.sql.DeltaSparkSessionExtension
spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl=org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri=http://unity-catalog:8080/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse=unity
spark.sql.catalog.iceberg.token=not_used

# S3/SeaweedFS (in-network service name)
spark.hadoop.fs.s3a.endpoint=http://seaweedfs:8333
spark.hadoop.fs.s3a.access.key=lakehouse_s3
spark.hadoop.fs.s3a.secret.key=lakehouse_s3_secret
spark.hadoop.fs.s3a.path.style.access=true
spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem

# Performance (defaults are fine for demos)
spark.driver.memory=4g
spark.executor.memory=8g
```

See `config/spark/spark-defaults.conf.example` for the complete, authoritative set
(including the catalog-managed Delta catalog and the required JARs).

### Spark version

This repo is **Spark 4.1 only**. Container is `spark-master-41` on port 7078 (UI 8082, worker UI 8083), running Java 21. For multi-version setups, use the upstream [`lakehouse-stack`](https://github.com/lisancao/lakehouse-stack) repo.

## Docker Compose Configuration

### Spark 4.1 (docker-compose-spark41.yml)

Mounts:
- `config/spark/spark-defaults.conf` → `/opt/spark/conf/spark-defaults.conf`
- `jars/` → `/opt/spark/jars-extra/`
- `scripts/` → `/scripts/`

### Repository structure (what's mounted where)

```
scripts/
├── tools/           # download-jars.sh, kafka-producer.py
├── connectivity/    # Per-service smoke scripts
└── testdata/        # Generator module

demos/               # Empty placeholders (per-demo READMEs)
dags/                # Airflow DAGs (demos add their own)
```

### Kafka (docker-compose-kafka.yml)

Default configuration:
- Zookeeper: port 2181
- Kafka broker: port 9092
- Single broker setup (development only)

## Resource Limits

For local development, recommended minimums:
- **Memory**: 8GB RAM (16GB recommended)
- **Disk**: 20GB free space (for JARs + data)
- **CPU**: 4 cores

Adjust Docker Desktop resources if needed:
- Docker Desktop → Settings → Resources

## Networking

The stack runs on a shared Docker **bridge network** (`lakehouse-network`):
- Containers reach each other by **service name** — e.g. Spark talks to
  `unity-catalog:8080`, `seaweedfs:8333`, `kafka:9092`, `postgres:5432`.
- Host-facing services **publish ports**, so from your machine you use
  `localhost:<published-port>` (e.g. `sc://localhost:15002`, `localhost:8081`
  for Unity Catalog, `localhost:8333` for S3).
- PostgreSQL and SeaweedFS are **Compose services** (see
  `docker-compose-storage.yml`), not host-installed — their data lives in named
  volumes.

Because the network is project-scoped, you can run isolated stacks side by side
by setting `COMPOSE_PROJECT_NAME` (the test harness does this). See the port
table in the top-level `CLAUDE.md` for the full published-port map.

## Validation

After configuration, validate with:

```bash
# Check all settings
./lakehouse setup

# Test connectivity
./lakehouse test

# View current status (JSON)
./lakehouse status --json
```

## Next Steps

- [CLI Reference](../guides/cli-reference.md) - All available commands
- [Troubleshooting](../troubleshooting.md) - Configuration issues
