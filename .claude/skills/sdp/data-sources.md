# SDP data sources

Reading non-SDP sources inside a pipeline. Every transformation starts with:

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

spark = SparkSession.active()
```

## Files (Parquet / JSON / CSV)

```python
@dp.materialized_view(name="bronze_files")
def bronze_files() -> DataFrame:
    return (
        spark.read.format("parquet")
        .schema("order_id STRING, amount DOUBLE, event_ts TIMESTAMP")  # declare schema
        .load("s3a://lakehouse/landing/orders/")
    )
```

Continuous file arrival — a streaming `@dp.table` over the file source:

```python
@dp.table(name="bronze_files_stream")
def bronze_files_stream() -> DataFrame:
    return (
        spark.readStream.format("parquet")
        .schema("order_id STRING, amount DOUBLE, event_ts TIMESTAMP")
        .option("maxFilesPerTrigger", 100)
        .load("s3a://lakehouse/landing/orders/")
    )
```

(Databricks Auto Loader / `cloudFiles` is not OSS — use the plain file-source
streaming reader.)

## Kafka

See [streaming.md](streaming.md).

## JDBC (external relational sources)

```python
@dp.materialized_view(name="bronze_customers")
def bronze_customers() -> DataFrame:
    return (
        spark.read.format("jdbc")
        .option("url", "jdbc:postgresql://localhost:5432/source_db")
        .option("dbtable", "public.customers")
        .option("user", "...")
        .option("password", "...")
        .load()
    )
```

Pull external JDBC into a bronze dataset, not directly from silver/gold —
pinning the snapshot at bronze keeps the pipeline deterministic.

## Existing tables (Delta / Iceberg, not SDP-owned)

```python
@dp.materialized_view(name="silver_from_external")
def silver_from_external() -> DataFrame:
    # An existing UC Delta table:
    return spark.read.table("unity.external.orders")
    # ...or an Iceberg table via the read-only iceberg catalog:
    # return spark.read.table("iceberg.external.orders")
```

`spark.sql("SELECT ... FROM unity.external.orders")` works too — SDP infers the
dependency from the table reference in the SQL string.

## Synthetic data (demos)

Don't use `spark.createDataFrame([...rows...])` — it triggers analysis and SDP
rejects it. Build lazily from `spark.range`:

```python
@dp.materialized_view(name="orders_bronze")
def orders_bronze() -> DataFrame:
    return spark.range(5).selectExpr(
        "id + 1 AS order_id",
        "concat('cust_', cast(id + 1 AS STRING)) AS customer",
        "(id + 1) * 10.0 AS amount",
    )
```

## Output format

On this stack SDP outputs **Delta** tables (Iceberg writes via UC are not
supported — UC OSS's Iceberg REST adapter is read-only). When the pipeline
targets `catalog: unity`, each table needs `table_properties={"location":
"s3://...", "provider": "delta"}` — see [unity-catalog.md](unity-catalog.md).

## REST / custom sources

OSS SDP pipeline functions should stay pure (return a DataFrame, no side
effects). Calling a REST API inside a function works but bakes the call into
every pipeline run and isn't idempotent. Prefer landing API data to files /
Kafka with a separate job, then ingesting that with SDP.
