# SDP streaming pipelines

A `@dp.table` whose function returns a streaming DataFrame (`spark.readStream...`)
becomes a **streaming table** — SDP manages offsets and checkpoints. Downstream
datasets that read it with `spark.readStream.table(...)` inherit the streaming
nature; ones that read it with `spark.read.table(...)` are batch materialized
views over the current snapshot.

## Kafka → streaming table

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

ORDER_SCHEMA = "order_id STRING, amount DOUBLE, event_ts TIMESTAMP"


@dp.table(name="orders_bronze", comment="Raw orders from Kafka.")
def orders_bronze() -> DataFrame:
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", "kafka:9092")
        .option("subscribe", "orders")
        .option("startingOffsets", "latest")
        .load()
        .select(
            f.from_json(f.col("value").cast("string"), ORDER_SCHEMA).alias("o"),
            f.col("timestamp").alias("_kafka_ts"),
        )
        .select("o.*", "_kafka_ts")
    )


@dp.table(name="orders_enriched", comment="Cleaned stream.")
def orders_enriched() -> DataFrame:
    # readStream.table → this stays a streaming table.
    return (
        spark.readStream.table("orders_bronze")
        .where("amount IS NOT NULL")
        .withColumn("order_date", f.to_date("event_ts"))
    )
```

`examples/python/01_streaming_table.py` in `lisancao/pyspark-sdp` is the
canonical version of this chain.

## Watermarks

Set a watermark before any stateful streaming op (dedup, windowed aggregation)
or state grows unbounded:

```python
@dp.table(name="orders_deduped")
def orders_deduped() -> DataFrame:
    return (
        spark.readStream.table("orders_bronze")
        .withWatermark("event_ts", "10 minutes")
        .dropDuplicatesWithinWatermark(["order_id"])
    )
```

## Checkpointing

SDP manages checkpoint locations from the pipeline `storage` path (the
`storage:` field in `spark-pipeline.yml`). **Do not** set `checkpointLocation`
inside a pipeline function — it conflicts with the managed location.

## Kafka timestamps

Kafka's `timestamp` column is fine as-is. But event-time fields inside the
payload often arrive as epoch-millis `LongType` — cast explicitly:

```python
f.to_timestamp(f.col("ts_ms") / 1000).alias("event_ts")
```

Use ISO-8601-with-timezone for any literal timestamps (`"2026-01-01T00:00:00Z"`),
never bare dates — they parse inconsistently.

## Common failures

- **`Initial offset ... could not be determined`** — topic empty at startup.
  Use `startingOffsets: "earliest"` or seed the topic first.
- **State store grows forever** — missing watermark before a stateful op.
- **Schema drift** — Kafka payload changed shape. SDP enforces the declared
  schema on read; add a column with a default or evolve the table.
- **Continuous/RTM expectations** — SDP streaming tables are micro-batch. For
  sub-second latency, use raw Structured Streaming Real-Time Mode, not SDP.
