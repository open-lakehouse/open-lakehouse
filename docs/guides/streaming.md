# Streaming Guide

Run real-time streaming pipelines with Kafka and Spark Structured Streaming.

## Architecture

```
┌──────────────┐      ┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Producer   │ ──── │    Kafka    │ ──── │    Spark     │ ──── │   Iceberg   │
│  (Python)    │      │   Broker    │      │  Streaming   │      │   Tables    │
└──────────────┘      └─────────────┘      └──────────────┘      └─────────────┘
                      (event queue)        (direct read)         (via catalog)
                                                  │
                                                  ▼
                                           ┌─────────────┐
                                           │ Checkpoints │
                                           │(exactly-once)│
                                           └─────────────┘
```

**Key points:**
- Kafka serves as an event queue (not managed by Iceberg catalog)
- Spark reads directly from Kafka topics
- Spark writes to Iceberg tables via the catalog
- Checkpoints enable exactly-once processing

## Quick Start

Terminal 1 - Start producer:
```bash
./lakehouse producer
```

Terminal 2 - Start consumer:
```bash
./lakehouse consumer
```

## Kafka Setup

Kafka starts automatically with `./lakehouse start all` or:
```bash
./lakehouse start kafka
```

Default configuration:
- Broker: `localhost:9092`
- Zookeeper: `localhost:2181`

### Kafka Commands

```bash
# List topics
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Create topic
docker exec kafka kafka-topics --create \
  --topic my-topic \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1

# Describe topic
docker exec kafka kafka-topics --describe \
  --topic my-topic \
  --bootstrap-server localhost:9092

# Console consumer (debug)
docker exec kafka kafka-console-consumer \
  --topic orders \
  --bootstrap-server localhost:9092 \
  --from-beginning
```

## Built-in Producers

### Synthetic Event Producer

Generates random events continuously:
```bash
./lakehouse producer
```

### Test Data Streamer

Streams pre-generated order events:
```bash
# Generate data first
./lakehouse testdata generate --days 1

# Stream at 60x speed
./lakehouse testdata stream --speed 60
```

## Spark Streaming

### Basic Consumer

The built-in consumer shows live aggregations:
```bash
./lakehouse consumer
```

### Custom Streaming Jobs

Example: `scripts/quickstarts/04-kafka-streaming.py`

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as f

spark = SparkSession.builder \
    .appName("KafkaStreaming") \
    .getOrCreate()

# Read from Kafka
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "orders") \
    .option("startingOffsets", "latest") \
    .load()

# Parse JSON
parsed = df.select(
    f.from_json(
        f.col("value").cast("string"),
        "event_type STRING, order_id STRING, ts STRING"
    ).alias("data")
).select("data.*")

# Windowed aggregation
result = parsed \
    .withWatermark("ts", "10 minutes") \
    .groupBy(
        f.window("ts", "5 minutes"),
        "event_type"
    ) \
    .count()

# Output to console
query = result.writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate", False) \
    .start()

query.awaitTermination()
```

Run with:
```bash
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.0 \
  /scripts/quickstarts/04-kafka-streaming.py
```

### Write to Iceberg

```python
# Write stream to Iceberg table
query = parsed.writeStream \
    .format("iceberg") \
    .outputMode("append") \
    .option("path", "iceberg.bronze.events_stream") \
    .option("checkpointLocation", "/tmp/checkpoint") \
    .start()
```

## Streaming Patterns

### At-Least-Once Delivery

Default behavior. Events may be processed multiple times on failure.

```python
df.writeStream \
    .format("iceberg") \
    .option("checkpointLocation", "/tmp/checkpoint") \
    .start()
```

### Exactly-Once with Iceberg

Iceberg provides exactly-once semantics:

```python
df.writeStream \
    .format("iceberg") \
    .outputMode("append") \
    .option("fanout-enabled", "true") \
    .option("checkpointLocation", "/tmp/checkpoint") \
    .trigger(processingTime="10 seconds") \
    .start()
```

### Watermarks and Late Data

Handle late-arriving events:

```python
df.withWatermark("event_time", "1 hour") \
    .groupBy(
        f.window("event_time", "10 minutes"),
        "category"
    ) \
    .count()
```

## Monitoring

### Spark Streaming UI

While a streaming job runs:
- http://localhost:4040/streaming/

Shows:
- Batch processing times
- Input rate
- Processing rate
- Scheduling delay

### Kafka Metrics

```bash
# Consumer group lag
docker exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe \
  --group spark-kafka-source-*
```

## Troubleshooting

### Consumer Not Receiving Messages

```bash
# Check Kafka is running
./lakehouse test

# Check topic exists
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Check messages in topic
docker exec kafka kafka-console-consumer \
  --topic orders \
  --bootstrap-server localhost:9092 \
  --from-beginning \
  --max-messages 5
```

### Slow Processing

- Increase `spark.sql.shuffle.partitions`
- Check for data skew in `groupBy` keys
- Use appropriate watermark intervals

### Checkpoint Errors

```bash
# Clear checkpoint on schema changes
rm -rf /tmp/checkpoint

# Use versioned checkpoint paths
.option("checkpointLocation", "/tmp/checkpoint/v2")
```

## See Also

- [Test Data Generation](test-data.md)
- [CLI Reference](cli-reference.md)
- [Spark Streaming Docs](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
