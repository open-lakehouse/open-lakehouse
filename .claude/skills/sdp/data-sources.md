# SDP data sources

Reading from non-SDP sources inside a pipeline.

## Files (Parquet/JSON/CSV)

```python
@dlt.table
def bronze_files():
    return (spark.read
            .format("parquet")
            .schema(MY_SCHEMA)              # always declare schema
            .load("s3a://landing/orders/"))
```

For continuous arrival, use `readStream` + `cloudFiles` (Auto Loader equivalent — partial in OSS Spark; fall back to file-source streaming):

```python
@dlt.table
def bronze_files_stream():
    return (spark.readStream
            .format("parquet")
            .schema(MY_SCHEMA)
            .option("maxFilesPerTrigger", 100)
            .load("s3a://landing/orders/"))
```

## JDBC (external relational sources)

```python
@dlt.table
def bronze_postgres():
    return (spark.read.format("jdbc")
            .option("url", "jdbc:postgresql://host:5432/db")
            .option("dbtable", "public.customers")
            .option("user", "${secrets.pg_user}")
            .option("password", "${secrets.pg_pass}")
            .load())
```

Prefer pulling into bronze rather than reading JDBC directly from silver/gold — pinning a snapshot makes the pipeline deterministic.

## Kafka

See [streaming.md](streaming.md).

## REST / custom

Wrap in a regular `@dlt.table` whose function pulls via `requests`, returns a DataFrame:

```python
import dlt, requests
from pyspark.sql.types import StructType, StructField, StringType

@dlt.table
def bronze_api():
    resp = requests.get("https://api.example.com/orders", timeout=30)
    resp.raise_for_status()
    return spark.createDataFrame(resp.json(), schema=API_SCHEMA)
```

This bakes the API call into pipeline execution. Cache aggressively at the bronze layer — don't re-call the API from silver.

## Iceberg tables (existing, not SDP-owned)

```python
@dlt.table
def silver_external():
    return (spark.read.format("iceberg").load("iceberg.external.orders"))
```

Or via SQL:

```python
@dlt.table
def silver_external():
    return spark.sql("SELECT * FROM iceberg.external.orders")
```

## Delta tables

```python
@dlt.table
def silver_delta_input():
    return spark.read.format("delta").load("s3a://warehouse/delta/orders")
```

Works inside the same pipeline as Iceberg outputs — SDP doesn't care about format on the read side.

## File-format choice for SDP outputs

In `pipeline.yml`:

```yaml
configuration:
  pipelines.table.format: "iceberg"     # default for this stack
  # or "delta"
```

Per-table override via decorator:

```python
@dlt.table(table_properties={"pipelines.table.format": "delta"})
def silver_orders():
    ...
```

Iceberg is the default for the open-lakehouse stack. Use Delta only when downstream consumers require it.
