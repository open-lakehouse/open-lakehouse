---
name: kafka-streaming
description: Kafka 3.6 producer/consumer patterns for this stack. Load when wiring Kafka into a Spark job, debugging stream lag, or writing demo producers. Covers topic creation, Structured Streaming integration, schema serialization, and the local test harness.
---

# Kafka streaming

This stack runs Kafka 3.6 (Confluent Platform 7.5) + Zookeeper via `docker-compose-kafka.yml`. Broker is on `localhost:9092` (`kafka:9092` from inside the docker network). Auto-topic-creation is enabled by default.

## Topic ops

```bash
# List
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Create
docker exec kafka kafka-topics --create --topic orders \
  --partitions 3 --replication-factor 1 \
  --bootstrap-server localhost:9092

# Describe
docker exec kafka kafka-topics --describe --topic orders --bootstrap-server localhost:9092

# Consume (CLI)
docker exec -it kafka kafka-console-consumer --topic orders \
  --from-beginning --bootstrap-server localhost:9092
```

## Spark Structured Streaming reader

```python
from pyspark.sql import functions as f
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

ORDER = StructType([
    StructField("order_id", StringType(), False),
    StructField("amount",   DoubleType(), False),
    StructField("event_ts", TimestampType(), False),
])

orders = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "orders")
    .option("startingOffsets", "latest")
    .option("failOnDataLoss", "false")     # demo-safe; set true for prod
    .load()
    .select(
        f.from_json(f.col("value").cast("string"), ORDER).alias("o"),
        f.col("timestamp").alias("_kafka_ts"),
        f.col("partition"),
        f.col("offset"),
    )
    .select("o.*", "_kafka_ts", "partition", "offset")
)

(orders.writeStream
   .format("iceberg")
   .option("checkpointLocation", "s3a://warehouse/_checkpoints/bronze_orders/")
   .outputMode("append")
   .trigger(processingTime="30 seconds")
   .toTable("iceberg.bronze.orders"))
```

## Spark Kafka writer

```python
(df.selectExpr("CAST(order_id AS STRING) AS key", "to_json(struct(*)) AS value")
   .write.format("kafka")
   .option("kafka.bootstrap.servers", "kafka:9092")
   .option("topic", "orders.normalized")
   .save())
```

## Python producer (demo data)

The repo ships `scripts/tools/kafka-producer.py` for emitting test events. Usage:

```bash
./lakehouse producer
```

Or call it directly: `poetry run python scripts/tools/kafka-producer.py --rate 10 --topic orders`.

For larger volumes use the testdata streamer:

```bash
./lakehouse testdata stream --speed 60   # 60× wall-clock rate
```

## Connect from outside Docker

The compose maps `9092:9092` so host clients can reach Kafka via `localhost:9092`. The advertised listener is `PLAINTEXT://localhost:9092` for that reason. From inside the docker network, use `kafka:9092`.

## Common pitfalls

- **`startingOffsets: latest` against an empty topic** → stream sits idle forever. Either seed the topic or use `earliest`.
- **No checkpoint location** → Structured Streaming will recompute from `startingOffsets` every restart. Always specify `checkpointLocation`.
- **Schema drift in JSON** → `from_json` returns NULL for unmapped fields silently. Validate with an `expect` (if SDP) or an explicit null check.
- **`failOnDataLoss: true` + a deleted partition** → stream aborts. For demos `false` is safer; for prod, fix the root cause.

## Performance defaults

- 3 partitions × 1 replica is fine for single-node demo. For more parallelism, bump partitions to `2 * spark.executor.cores * spark.executor.instances`.
- `maxOffsetsPerTrigger` caps per-batch work — useful when catching up from `earliest` against a large backlog.

## When to use Kafka vs file streaming

- Real-time event ingestion, sub-minute latency → Kafka.
- Files arriving in S3 (logs, batch dumps) → Structured Streaming file source. Don't wrap a file producer in Kafka unless you need fan-out.
