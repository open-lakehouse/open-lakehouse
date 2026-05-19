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

```bash
# PostgreSQL (Iceberg catalog)
POSTGRES_USER=lakehouse
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=host.docker.internal  # or localhost
POSTGRES_PORT=5432

# SeaweedFS (S3-compatible storage)
S3_ENDPOINT=http://host.docker.internal:8333
S3_ACCESS_KEY=any_string_here
S3_SECRET_KEY=any_string_here
S3_BUCKET=lakehouse
S3_WAREHOUSE=s3a://lakehouse/warehouse

# Iceberg (derived from above)
ICEBERG_CATALOG_URI=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/iceberg_catalog
ICEBERG_WAREHOUSE=${S3_WAREHOUSE}
```

### Host Configuration

| Environment | POSTGRES_HOST | S3_ENDPOINT |
|-------------|---------------|-------------|
| macOS/Windows Docker | `host.docker.internal` | `http://host.docker.internal:8333` |
| Linux Docker | `172.17.0.1` or `localhost` | `http://172.17.0.1:8333` |
| Native (no Docker) | `localhost` | `http://localhost:8333` |

## Spark Configuration

Create from the template:
```bash
cp config/spark/spark-defaults.conf.example config/spark/spark-defaults.conf
```

### Key Settings

```properties
# Iceberg via Unity Catalog REST (the only catalog mode in this repo)
spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl=org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri=http://localhost:8081/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse=unity
spark.sql.catalog.iceberg.token=not_used

# S3/SeaweedFS
spark.hadoop.fs.s3a.endpoint=http://localhost:8333
spark.hadoop.fs.s3a.access.key=your_access_key
spark.hadoop.fs.s3a.secret.key=your_secret_key
spark.hadoop.fs.s3a.path.style.access=true
spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem

# Performance (defaults are fine for demos)
spark.driver.memory=4g
spark.executor.memory=8g
```

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

## Network Modes

The stack uses `network_mode: host` for Docker containers, meaning:
- Containers share the host's network namespace
- No port mapping needed (containers bind directly)
- Services communicate via `localhost`

This simplifies configuration but requires:
- No conflicting services on the same ports
- PostgreSQL and SeaweedFS running on the host

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
