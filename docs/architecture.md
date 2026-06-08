# Architecture

System design for the open-lakehouse demo platform. Seven services, one catalog, one Spark version. Everything runs in Docker for local; the same shape deploys to AWS via `terraform/`.

## High-level diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                                     │
│                                                                              │
│  PySpark (sc://...)  •  spark-pipelines (SDP)  •  DuckDB  •  PyIceberg       │
│  Trino  •  notebooks                                                         │
└──────────┬──────────────────────────────────────────────────────┬────────────┘
           │ Spark Connect gRPC                                   │ Iceberg REST
           │ sc://localhost:15002                                 │ (multi-engine)
           ▼                                                      │
┌──────────────────────────────────────────┐                      │
│   COMPUTE                                │                      │
│                                          │                      │
│   spark-connect-41   :15002 (gRPC)       │                      │
│   spark-master-41    :7078 (UI :8082)    │                      │
│   spark-worker-41          (UI :8083)    │                      │
│                                          │   ┌──────────────────┘
│   ┌──────┐  ┌──────┐  ┌────────┐         │   │
│   │BRONZE│─▶│SILVER│─▶│  GOLD  │         │   │
│   └──────┘  └──────┘  └────────┘         │   │
└──────────┬───────────────────────────────┘   │
           │ Iceberg REST API                  │
           ▼                                   ▼
┌──────────────────────────────────────────────────────┐
│   CATALOG                                            │
│                                                      │
│   Unity Catalog OSS   :8081                          │
│   ├─ /api/2.1/unity-catalog/...    (UC native)       │
│   ├─ /api/2.1/unity-catalog/iceberg/v1/...  (REST)   │
│   └─ Delta-native API                                │
│                                                      │
│   PostgreSQL          :5432                          │
│   └─ UC metastore backing store                      │
└──────────────────────────┬───────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│   STORAGE                                            │
│                                                      │
│   SeaweedFS (S3 API)  :8333                          │
│   └─ s3://warehouse/                                 │
│       ├─ bronze/                                     │
│       ├─ silver/                                     │
│       └─ gold/                                       │
└──────────────────────────────────────────────────────┘

                Kafka :9092 / Zookeeper :2181 stream events into the
                Spark Connect client, which writes to Iceberg via UC.
```

## Catalog: Unity Catalog OSS only

This stack uses **Unity Catalog OSS as the only Iceberg catalog**. The legacy PostgreSQL JDBC catalog path is removed. UC OSS exposes the standard Iceberg REST Catalog API at `http://localhost:8081/api/2.1/unity-catalog/iceberg`, which any Iceberg client speaks (Spark, DuckDB, PyIceberg, Trino, Dremio).

Spark sees this as:

```
spark.sql.catalog.iceberg                org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl   org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri            http://localhost:8081/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse      unity
```

UC OSS persists its catalog metadata in a PostgreSQL database (`unitycatalog` schema). This is invisible to clients — they only touch the REST endpoint.

### Why UC OSS, not JDBC catalog or Hive metastore

- **Multi-engine reads.** DuckDB, Trino, etc. speak Iceberg REST natively. JDBC catalog binds you to clients that know SparkCatalog.
- **Credential vending.** UC can mint short-lived S3 credentials per request; clients don't ship hardcoded keys.
- **Format flexibility.** UC OSS 0.4.x handles Iceberg, Delta, and Hudi (the latter via UniForm projection).

## Open table formats

| Format | When to use | Where it lives |
|--------|-------------|----------------|
| **Iceberg 1.10** | Default. Most demos. UC OSS surfaces it natively. | Catalog: `iceberg.<schema>.<table>` |
| **Delta 4.0** | Demos that explicitly show Delta features, or hand-off to Databricks. | Catalog: `spark_catalog.<schema>.<table>` |

Both run in the same Spark session. To enable Delta alongside Iceberg, extend `spark.sql.extensions`:

```
spark.sql.extensions  org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,io.delta.sql.DeltaSparkSessionExtension
```

## Streaming: Kafka → Spark → Iceberg

Kafka is **not** registered in the catalog. It's an event bus that Spark Structured Streaming reads from directly. Bronze tables land the events; silver and gold derive from bronze with declarative pipelines (see [`.claude/skills/sdp/`](../.claude/skills/sdp/)).

```
                  Spark Connect client (sc://localhost:15002)
                                  │
                                  ▼
Kafka topic ──readStream──▶  Spark SS  ──writeStream──▶  iceberg.bronze.<table>
                                                                  │
                                                          spark-pipelines run
                                                          (SDP, Connect-backed)
                                                                  ▼
                                                          iceberg.silver.<table>
                                                                  │
                                                                  ▼
                                                          iceberg.gold.<table>
```

Checkpoints live under `s3://warehouse/_checkpoints/<dataset>/` so streams resume cleanly after restart.

## Orchestration: Airflow 3.1

Airflow doesn't own the data — it orchestrates *when* things run. Patterns:

- Daily Iceberg compaction + snapshot expiration.
- Triggering SDP pipelines on schedule.
- Sensor → action loops over Kafka topics or S3 prefixes.

DAGs live in `dags/`. The compose file mounts that directory into all Airflow containers. See [`.claude/skills/airflow-3/`](../.claude/skills/airflow-3/) for the 2→3 migration gotchas and recommended DAG shape.

## Experiment tracking: MLflow 3.1

Tracking server on `:5000`, AI Gateway on `:5001`. Backend store is PostgreSQL (`mlflow` database). Artifact store is SeaweedFS (`s3://mlflow/`). The AI Gateway routes LLM calls to Anthropic or local Ollama via `config/mlflow/gateway-config.yml`.

## Storage: SeaweedFS

S3-compatible object storage running locally. Endpoint: `localhost:8333`. Same code that writes to SeaweedFS reads from real S3 in AWS deployments — just change the endpoint and credentials.

Path layout under `s3://warehouse/`:

```
warehouse/
├── bronze/<table>/    (Iceberg-managed)
├── silver/<table>/
├── gold/<table>/
├── delta/<table>/     (Delta-managed)
└── _checkpoints/<dataset>/
```

## Ports

| Service | Port | UI |
|---------|------|-----|
| PostgreSQL | 5432 | — |
| SeaweedFS | 8333 | — |
| Spark master | 7078 | 8082 (worker UI 8083) |
| Spark Connect | 15002 | gRPC (no UI) |
| Kafka | 9092 | — |
| Zookeeper | 2181 | — |
| Unity Catalog | 8081 | (REST only) |
| Airflow | 8085 | 8085 |
| MLflow Tracking | 5000 | 5000 |
| MLflow AI Gateway | 5001 | — |

## Transport: Connect-first

The default and only supported transport is **Spark Connect**. The Connect server runs in container `spark-connect-41` and clients connect via `SparkSession.builder.remote("sc://localhost:15002")`. The `./lakehouse` CLI exports `LAKEHOUSE_SPARK_REMOTE` for downstream tools to read.

This matters because **Spark Declarative Pipelines (SDP) requires Connect** — `pyspark.pipelines` uses `SparkConnectGraphElementRegistry` internally even though `spark-pipelines run` doesn't open `sc://` explicitly. Disabling the Connect server breaks the SDP demo path.

A `--spark-local` flag exists on the CLI as a forward-compat stub for an eventual in-process Spark mode (no Docker, no Connect, classic SparkSession). Today it exits with "not yet implemented"; the placeholder demo lives at `demos/local-mode-spark/`.

## Version pins

| Component | Version | Why pinned |
|-----------|---------|------------|
| Spark | 4.1.0 | Scala 2.13, Java 21 |
| Iceberg | 1.10.0 | `iceberg-spark-runtime-4.0_2.13-1.10.0.jar` covers Spark 4.0+ |
| Delta | 4.2.0 | Compatible with Spark 4.1 |
| Hadoop | 3.4.1 | Bundled in Spark image |
| AWS SDK v2 | 2.24.6 | Exact match for Hadoop 3.4.1 |
| Airflow | 3.1.6 | Breaking changes from 2.x — see airflow-3 skill |
| Unity Catalog OSS | 0.4.0 | Catalog-managed commits, Iceberg REST |
| MLflow | 3.1 | AI Gateway needs ≥ 3.0 |

Don't change these without testing both the connectivity suite and at least one streaming demo end-to-end.

## Compose file map

| File | Defines |
|------|---------|
| `docker-compose-spark41.yml` | Spark master + worker |
| `docker-compose-kafka.yml` | Kafka + Zookeeper |
| `docker-compose-airflow.yml` | Webserver, scheduler, triggerer, init |
| `docker-compose-unity-catalog.yml` | UC OSS server |
| `docker-compose-mlflow.yml` | MLflow tracking + AI Gateway |
| `docker-compose-notebooks.yml` | JupyterLab (optional) |

These are intentionally separate so you can spin up only what a demo needs. The `lakehouse` CLI handles the dispatch.

## AWS deployment shape

`terraform/` provisions:

- VPC + subnets
- RDS PostgreSQL (replaces the local one)
- S3 bucket (replaces SeaweedFS — the same Iceberg writes land here)
- EC2 instances running the same compose files via systemd

The `.env` file changes endpoint URLs; everything else is identical to local. See [`docs/deployment/aws.md`](deployment/aws.md).

Optional Databricks-managed destination (`terraform-databricks/`) for demos that show OSS → managed-platform hand-off.

## Repository layout

```
open-lakehouse/
├── lakehouse                         # CLI
├── docker-compose-*.yml              # Service definitions
├── config/                           # Per-service configs (UC, Spark, MLflow, Airflow)
├── docker/                           # Custom Dockerfiles (Airflow, Jupyter, MLflow)
├── docs/                             # Human-facing docs
├── demos/                            # Empty per-demo placeholders + template
├── dags/                             # Airflow DAGs (gitkeep — demos add their own)
├── schemas/                          # PostgreSQL migrations
├── scripts/
│   ├── connectivity/                 # Per-service smoke scripts
│   ├── testdata/                     # Generator
│   └── tools/                        # download-jars.sh etc.
├── tests/                            # pytest unit + integration
├── terraform/                        # AWS self-hosted
├── terraform-databricks/             # Databricks managed destination
└── .claude/                          # AI scaffolding (skills + agent prompts)
```

## What's intentionally NOT in this repo

- Spark 4.0 (use upstream `lakehouse-stack`).
- PostgreSQL JDBC catalog (deprecated path — UC OSS only).
- Benchmarks (separate concern from demos).
- Production hardening (auth, secret rotation, multi-AZ).
- Alternative catalogs (Polaris, Nessie, Glue).
- Lance / advanced storage formats (not in the demo scope).
