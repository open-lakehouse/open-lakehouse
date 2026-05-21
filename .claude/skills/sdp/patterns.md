# SDP patterns

Common shapes, in the OSS `pyspark.pipelines` API. Runnable reference
implementations live in [`lisancao/pyspark-sdp`](https://github.com/lisancao/pyspark-sdp)
under `src/pyspark_sdp/patterns/` and `examples/python/`.

Every transformation file starts the same way:

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()
```

## Medallion: bronze → silver → gold

```python
# BRONZE — raw ingest. External source → @dp.table (streaming table).
@dp.table(name="orders_bronze", comment="Raw orders.")
def orders_bronze() -> DataFrame:
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", "kafka:9092")
        .option("subscribe", "orders")
        .load()
        .select(
            f.from_json(f.col("value").cast("string"),
                        "order_id STRING, amount DOUBLE, event_ts TIMESTAMP").alias("o"),
            f.current_timestamp().alias("_ingested_at"),
        )
        .select("o.*", "_ingested_at")
    )

# SILVER — cleaned. Derives from an SDP table → @dp.materialized_view.
@dp.materialized_view(name="orders_silver", comment="Cleaned, deduplicated.")
def orders_silver() -> DataFrame:
    return (
        spark.read.table("orders_bronze")        # dependency inferred from this read
        .dropDuplicates(["order_id"])
        .withColumn("order_date", f.to_date("event_ts"))
        .where("amount >= 0")
    )

# GOLD — aggregated.
@dp.materialized_view(name="orders_gold", comment="Daily revenue.")
def orders_gold() -> DataFrame:
    return (
        spark.read.table("orders_silver")
        .groupBy("order_date")
        .agg(f.sum("amount").alias("revenue"), f.count("*").alias("order_count"))
    )
```

Three datasets, three tiers. SDP orders them from the `spark.read.table(...)`
calls — never refer forward to a not-yet-defined dataset.

`demos/sdp-medallion/` is a working version of this pattern materialized into
Unity Catalog. Note: when targeting `catalog: unity`, every table needs
`table_properties={"location": "s3://...", "provider": "delta"}` — see
[unity-catalog.md](unity-catalog.md).

## Quarantine (data quality — the OSS substitute for expectations)

OSS SDP has **no** `@dp.expect*` decorators. Route invalid rows to a separate
table by registering two `@dp.table`s that filter the same source on a boolean
predicate and its negation:

```python
from pyspark.sql.functions import expr

def with_quarantine(name, quarantine_name, source_table, validation,
                     streaming=True):
    """Register a clean table + a quarantine table off one source."""
    pred = expr(validation)

    @dp.table(name=name)
    def _clean() -> DataFrame:
        reader = spark.readStream if streaming else spark.read
        return reader.table(source_table).filter(pred)

    @dp.table(name=quarantine_name)
    def _quarantine() -> DataFrame:
        reader = spark.readStream if streaming else spark.read
        return reader.table(source_table).filter(~pred)

    return _clean, _quarantine

# usage
with_quarantine("orders_valid", "orders_quarantine", "orders_bronze",
                "amount > 0 AND order_id IS NOT NULL")
```

The source is read twice; Spark's optimizer usually shares the scan (verify
with `.explain()`). `validation` must be a SQL expression / Column — arbitrary
Python callables need a UDF, which kills predicate pushdown. This is the
`patterns/quarantine.py` shape from `lisancao/pyspark-sdp`.

## Deduplication

Dedup in a **SQL** transformation — a `row_number()` window keeps one row per
key:

```sql
CREATE MATERIALIZED VIEW orders_deduped AS
SELECT * EXCEPT (_rn) FROM (
  SELECT *, row_number() OVER (PARTITION BY order_id ORDER BY event_ts DESC) AS _rn
  FROM orders_bronze
) WHERE _rn = 1;
```

Do **not** use `DataFrame.dropDuplicates(["order_id"])` inside a *Python*
pipeline function. The column-subset form eagerly resolves the upstream
DataFrame's schema against the live catalog — but an upstream SDP dataset is
not a catalog table during graph construction, so registration fails with
`[TABLE_OR_VIEW_NOT_FOUND]`. Keep dedup in SQL, or do it downstream of
materialization. (Verified on Spark 4.1 + Connect, 2026-05-21.)

For streaming dedup, set a watermark first so state is bounded — see
[streaming.md](streaming.md).

## Slowly-changing dimensions / CDC

**Auto CDC (`create_auto_cdc_flow` / `APPLY CHANGES INTO`) is Databricks-only**
— SPARK-56249 is not merged into OSS Spark 4.1. For SCD in OSS SDP today you
hand-roll it: a streaming `@dp.table` for the change feed, then a
`@dp.materialized_view` that computes current-state with window functions, or
an `@dp.append_flow` into a streaming table. Don't reach for `dp.apply_changes`
— it doesn't exist.

## Idempotent re-runs

SDP datasets are recomputed deterministically on re-run. To force a full
recompute: `spark-pipelines run --full-refresh-all` (or `--full-refresh
<dataset>`). Note: re-running over an existing **UC** table can fail —
UC's connector doesn't support truncate; drop the table first
([unity-catalog.md](unity-catalog.md)).

## Common mistakes

- `import dlt` — wrong framework. `from pyspark import pipelines as dp`.
- Forgetting `spark = SparkSession.active()` — OSS SDP does not inject `spark`.
- `spark.createDataFrame([...rows...])` inside a function — triggers analysis,
  rejected. Use `spark.range(n).selectExpr(...)` for synthetic data.
- Passing an upstream dataset as a function arg — breaks DAG inference. Read it
  inside the body.
- `spark.sql("CREATE TABLE ...")` inside a pipeline — SDP owns the DDL.
- Reading a downstream dataset — cycles are rejected; the DAG is acyclic.
