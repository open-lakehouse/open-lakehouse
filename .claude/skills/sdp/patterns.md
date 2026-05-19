# SDP patterns

Common shapes you'll write inside an SDP pipeline.

## Medallion: bronze → silver → gold

```python
import dlt
from pyspark.sql import functions as f

# BRONZE — raw, append-only, no transformations beyond schema enforcement
@dlt.table(table_properties={"quality": "bronze"})
def bronze_orders():
    return (spark.read.format("iceberg").load("iceberg.landing.orders_raw")
            .withColumn("_ingested_at", f.current_timestamp()))

# SILVER — cleaned, deduplicated, typed
@dlt.table(table_properties={"quality": "silver"})
@dlt.expect_or_drop("valid_id", "order_id IS NOT NULL")
def silver_orders():
    return (dlt.read("bronze_orders")
            .dropDuplicates(["order_id"])
            .withColumn("order_date", f.to_date("event_ts"))
            .filter(f.col("amount") >= 0))

# GOLD — aggregated, business-readable
@dlt.table(table_properties={"quality": "gold"})
def gold_daily_revenue():
    return (dlt.read("silver_orders")
            .groupBy("order_date", "region")
            .agg(f.sum("amount").alias("revenue"),
                 f.count("*").alias("order_count")))
```

Three tables, three quality tiers. The SDP DAG runs them in order — never refer forward.

## Slowly changing dimension (type-2)

```python
@dlt.table
def dim_customer():
    return (dlt.read_stream("bronze_customer_changes")
            .selectExpr("customer_id", "name", "address", "event_ts AS valid_from")
            # SDP CDC API
            .transform(dlt.apply_changes(
                target="dim_customer",
                source="bronze_customer_changes",
                keys=["customer_id"],
                sequence_by="event_ts",
                stored_as_scd_type=2,
            )))
```

Use `dlt.apply_changes(..., stored_as_scd_type=1)` for overwrite-in-place semantics.

## Idempotent re-runs

SDP's tables are idempotent by default — re-running the pipeline overwrites the outputs deterministically (or, for streaming, picks up from the checkpoint). To force a clean re-run, drop the target tables manually or use the `--full-refresh` flag.

## Avoiding common mistakes

- Don't `spark.sql("CREATE TABLE ...")` inside an SDP pipeline. SDP owns the DDL.
- Don't read from a downstream dataset (cycle). The DAG is acyclic.
- Don't pass a non-deterministic config (`f.current_timestamp()` outside of an ingestion column) — breaks idempotence.
- Don't write to the same target as another SDP dataset. One target = one decorator.
