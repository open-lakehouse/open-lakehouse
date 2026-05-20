# SDP against Unity Catalog OSS

Running Spark Declarative Pipelines so the materialized tables land in **Unity
Catalog OSS** as Delta tables. This was verified end-to-end on 2026-05-19
against `newfrontdocker/unitycatalog:v0.4.1` + Spark 4.1 + Delta 4.2.0. The path
has sharp edges — this file is the map through them.

## TL;DR — the pattern that works

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

spark = SparkSession.active()


@dp.materialized_view(
    name="orders_bronze",
    comment="...",
    table_properties={
        # BOTH keys are mandatory for UC OSS. See "Why" below.
        "location": "s3://lakehouse/warehouse/sdp/bronze/orders_bronze",
        "provider": "delta",
    },
)
def orders_bronze() -> DataFrame:
    return spark.range(5).selectExpr("id AS order_id", "...")
```

Pipeline spec (`spark-pipeline.yml`):

```yaml
name: sdp-medallion
catalog: unity        # the UC-backed catalog (spark.sql.catalog.unity)
schema: bronze        # field is `schema` (or `database`) — NOT `target`
storage: file:///tmp/sdp-medallion-storage
libraries:
  - glob:
      include: transformations/**
```

## The three rules

### 1. Pass `location` via `table_properties`, never via SQL `LOCATION`

SDP's SQL parser **rejects** `CREATE MATERIALIZED VIEW ... LOCATION '...'`:

```
Operation not allowed: Specifying location is not supported for
CREATE MATERIALIZED VIEW statements. The storage location for a
pipeline dataset is managed by the pipeline itself.
```

But the Python `@dp.materialized_view(table_properties={...})` dict is
forwarded straight into the catalog's `createTable` `properties` map. UC's
Spark connector (`io.unitycatalog.spark.UCSingleCatalog`) reads `location`
from there. So: SQL transformations can't target UC; Python ones can.

### 2. Set `provider` alongside `location`

UC's connector has two assertions in `createTable`:

```scala
assert(location != null)                       // UCSingleCatalog
assert(properties.get("provider") != null)     // UCProxy
```

SDP populates neither by default. `location` you supply; `provider` you must
also supply (`"delta"`). Miss `provider` and you get a bare
`java.lang.AssertionError: assertion failed` with no message.

### 3. Use the `s3://` scheme, not `s3a://`

UC's credential-vending endpoint (`generateTemporaryPathCredentials`) only
accepts `s3`, `gs`, `abfs` schemes. An `s3a://` location returns:

```
400 INVALID_ARGUMENT: Unsupported URI scheme: s3a
```

Write `location` as `s3://...`. Hadoop still does the actual I/O via
`S3AFileSystem` — `spark-defaults.conf` maps `spark.hadoop.fs.s3.impl` to
`org.apache.hadoop.fs.s3a.S3AFileSystem` so the `s3://` scheme resolves.

## Why SDP+UC is harder than SDP+Hive/JDBC

SDP's `DatasetManager.materializeTable` calls `catalog.createTable(...)`
**without** going through Spark's analyzer, so the `LOCATION` property that
the analyzer normally computes (`warehouse.dir + catalog + schema + table`)
is absent. JDBC and Hive/Delta catalogs tolerate a null location — they
compute their own default from a warehouse config. **UC's connector asserts
instead.** It has no schema-level storage root to fall back to, because UC OSS
models every table's `storage_location` as required metadata (designed around
external locations + credential vending, not the Hive "metastore picks the
path" convention).

So SDP implicitly assumes the Hive convention; UC doesn't honor it; you bridge
the gap manually with `table_properties`.

## Running it

```bash
# Connect server and SDP's embedded driver both want port 15002 — stop the
# standalone Connect server while running SDP, restart it after.
docker stop spark-connect-41

docker exec spark-master-41 sh -c \
  'cd /tmp/sdp-medallion && spark-pipelines run'

docker start spark-connect-41
```

`spark-pipelines dry-run` validates the graph without writing. `run` executes.

## Pre-reqs the base Spark image is missing

`spark-pipelines` imports fail on a stock `apache/spark:4.1.0` image — the CLI
needs Python packages the image doesn't ship:

```
pyyaml  pandas  pyarrow  grpcio  grpcio-status  protobuf  zstandard
```

The open-lakehouse Spark image should pre-install these (see the Dockerfile).
Without them you get `ModuleNotFoundError` from `pyspark/pipelines/cli.py`.

## Things that will bite you

| Symptom | Cause | Fix |
|---------|-------|-----|
| `AnalysisException: CANNOT_MODIFY_STATIC_CONFIG` | `configuration:` block in the spec re-sets a static config (`spark.sql.extensions`, `spark.sql.warehouse.dir`, `spark.connect.grpc.binding.port`) | Set those in `spark-defaults.conf` only; keep the spec's `configuration:` block minimal |
| `PIPELINE_SPEC_UNEXPECTED_FIELD: target` | spec used `target:` | The field is `schema:` (or `database:`) |
| `ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION` | `spark.createDataFrame([...])` inside a `@dp.materialized_view` function | Build lazily — `spark.range(n).selectExpr(...)` or read a source |
| `Table does not support truncates` | re-running the pipeline over an existing UC table | Drop the UC table first, or materialize to a fresh path |
| schema-mismatch on re-run | Delta files on S3 hold the old schema | Drop the table AND clear its S3 prefix, or use a new `location` |
| bare `AssertionError: assertion failed` | missing `location` or `provider` in `table_properties` | Supply both |
| `Unsupported URI scheme: s3a` | `location` written as `s3a://` | Use `s3://` |

## What's NOT possible today

- **SDP → UC-managed Iceberg tables.** UC OSS's Iceberg REST adapter is
  read-only (no `POST` endpoints) and its native API rejects `ICEBERG` as a
  `data_source_format`. SDP-on-UC works for **Delta only**. See
  [[unity-catalog-oss]] for the full UC write-side limitations.
- **SQL `.sql` transformations targeting UC.** They can't carry `location`.
  Use Python transformations for any UC-targeted dataset.

## Reference demo

`demos/sdp-medallion/` is a working bronze→silver→gold pipeline built with
this pattern. Read its `README.md` for the run/teardown contract.
