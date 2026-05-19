# SDP streaming pipelines

SDP detects streaming datasets from the source — return a streaming DataFrame and the table becomes a streaming target with checkpointing managed by SDP.

## Kafka → Iceberg

```python
import dlt
from pyspark.sql import functions as f
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

ORDER_SCHEMA = StructType([
    StructField("order_id", StringType(), False),
    StructField("amount",   DoubleType(), False),
    StructField("event_ts", TimestampType(), False),
])

@dlt.table(table_properties={"quality": "bronze", "ingestion": "kafka"})
def bronze_orders():
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", "kafka:9092")
        .option("subscribe", "orders")
        .option("startingOffsets", "latest")
        .load()
        .select(f.from_json(f.col("value").cast("string"), ORDER_SCHEMA).alias("o"),
                f.col("timestamp").alias("_kafka_ts"))
        .select("o.*", "_kafka_ts")
    )
```

The downstream `silver_orders` (defined with `dlt.read_stream("bronze_orders")`) inherits the streaming nature.

## Trigger modes

In `pipeline.yml`:

```yaml
configuration:
  pipelines.trigger.interval: "1 minute"     # micro-batch interval
  # or
  pipelines.trigger.continuous: "true"       # continuous mode (experimental in 4.1)
```

For demo purposes, micro-batch with a 30s–60s trigger is usually right.

## Watermarks

Always set a watermark before stateful streaming operations (dedup, aggregations):

```python
@dlt.table
def silver_orders():
    return (dlt.read_stream("bronze_orders")
            .withWatermark("event_ts", "10 minutes")
            .dropDuplicatesWithinWatermark(["order_id"]))
```

Without a watermark, state grows unbounded.

## Checkpointing

SDP manages checkpoint locations under the warehouse path automatically — `<warehouse>/_checkpoints/<dataset>/`. Do not configure `checkpointLocation` explicitly inside an SDP function; it conflicts with the managed location.

## Common failures

- **`StreamingQueryException: Initial offset for ... could not be determined`** — your Kafka topic has no records yet at startup. Use `startingOffsets: "earliest"` or seed the topic first.
- **State store size grows forever** — missing watermark. Add `withWatermark` and a stateful op that respects it.
- **Schema drift breaks the stream** — Kafka payload schema changed. SDP enforces declared schema on read; either add a column with a default or evolve the table via `ALTER TABLE`.
