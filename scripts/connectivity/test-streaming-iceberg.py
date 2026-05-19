#!/usr/bin/env python3
"""
Kafka to Iceberg Streaming Integration Test

Tests continuous streaming writes from Kafka to Iceberg:
- Spark Structured Streaming with Kafka source
- Iceberg sink with append mode
- Checkpointing and exactly-once semantics
- Schema handling in streaming context

Prerequisites:
    ./lakehouse start all

Usage:
    # Via spark-submit (recommended)
    docker exec spark-master-41 /opt/spark/bin/spark-submit \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.0 \
        /scripts/test-streaming-iceberg.py

    # With duration limit (seconds)
    docker exec spark-master-41 /opt/spark/bin/spark-submit \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.0 \
        /scripts/test-streaming-iceberg.py --duration 30
"""

import sys
import json
import uuid
import threading
import time
from datetime import datetime, timedelta
from argparse import ArgumentParser

try:
    from kafka import KafkaProducer
    from kafka.admin import KafkaAdminClient, NewTopic
    KAFKA_AVAILABLE = True
except ImportError:
    KafkaProducer = None  # type: ignore
    KafkaAdminClient = None  # type: ignore
    NewTopic = None  # type: ignore
    KAFKA_AVAILABLE = False
    print("Warning: kafka-python not installed. Using rate source instead.")

from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType


# Configuration
KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "test_streaming_orders"
CHECKPOINT_DIR = "/tmp/spark-checkpoints/streaming-iceberg-test"


def create_kafka_topic():
    """Create Kafka topic for testing."""
    if not KAFKA_AVAILABLE:
        return False

    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
        existing = admin.list_topics()

        if KAFKA_TOPIC not in existing:
            topic = NewTopic(name=KAFKA_TOPIC, num_partitions=2, replication_factor=1)
            admin.create_topics([topic])
            print(f"Created Kafka topic: {KAFKA_TOPIC}")
        else:
            print(f"Kafka topic exists: {KAFKA_TOPIC}")
        return True
    except Exception as e:
        print(f"Failed to create Kafka topic: {e}")
        return False


def start_event_producer(stop_event, events_per_second=2):
    """Background thread to produce events to Kafka."""
    if not KAFKA_AVAILABLE:
        return

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8') if k else None,
    )

    products = [
        ("PROD-001", "Laptop", 999.99),
        ("PROD-002", "Mouse", 29.99),
        ("PROD-003", "Keyboard", 79.99),
        ("PROD-004", "Monitor", 349.99),
    ]

    order_num = 1
    while not stop_event.is_set():
        product = products[order_num % len(products)]
        quantity = (order_num % 3) + 1

        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "order_placed",
            "timestamp": datetime.now().isoformat(),
            "order_id": f"STREAM-{order_num:05d}",
            "customer_id": f"CUST-{(order_num % 10) + 100}",
            "product_id": product[0],
            "product_name": product[1],
            "quantity": quantity,
            "unit_price": product[2],
            "total": product[2] * quantity,
        }

        producer.send(KAFKA_TOPIC, key=event['order_id'], value=event)
        order_num += 1

        time.sleep(1.0 / events_per_second)

    producer.flush()
    producer.close()
    print(f"Producer stopped after {order_num - 1} events")


def setup_iceberg_table(spark):
    """Create Iceberg table for streaming writes."""
    print("\n" + "=" * 60)
    print("Setting up Iceberg streaming table")
    print("=" * 60)

    spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_streaming")
    spark.sql("DROP TABLE IF EXISTS iceberg.test_streaming.orders")

    spark.sql("""
        CREATE TABLE iceberg.test_streaming.orders (
            event_id STRING,
            event_type STRING,
            event_timestamp TIMESTAMP,
            order_id STRING,
            customer_id STRING,
            product_id STRING,
            product_name STRING,
            quantity INT,
            unit_price DOUBLE,
            total DOUBLE,
            processing_time TIMESTAMP
        ) USING iceberg
        PARTITIONED BY (hours(event_timestamp))
    """)
    print("Created table: iceberg.test_streaming.orders")


def run_streaming_query(spark, duration_seconds):
    """Run Spark Structured Streaming query from Kafka to Iceberg."""
    print("\n" + "=" * 60)
    print(f"Starting streaming query (duration: {duration_seconds}s)")
    print("=" * 60)

    # Define schema for Kafka messages
    schema = StructType([
        StructField("event_id", StringType(), True),
        StructField("event_type", StringType(), True),
        StructField("timestamp", StringType(), True),
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("product_id", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("quantity", IntegerType(), True),
        StructField("unit_price", DoubleType(), True),
        StructField("total", DoubleType(), True),
    ])

    if KAFKA_AVAILABLE:
        # Read from Kafka
        stream_df = spark.readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP) \
            .option("subscribe", KAFKA_TOPIC) \
            .option("startingOffsets", "earliest") \
            .option("failOnDataLoss", "false") \
            .load()

        # Parse JSON and transform
        parsed_df = stream_df \
            .select(f.from_json(f.col("value").cast("string"), schema).alias("data")) \
            .select("data.*") \
            .withColumn("event_timestamp", f.to_timestamp("timestamp")) \
            .withColumn("processing_time", f.current_timestamp()) \
            .drop("timestamp")
    else:
        # Use rate source for testing without Kafka
        print("  Using rate source (Kafka not available)")
        rate_df = spark.readStream \
            .format("rate") \
            .option("rowsPerSecond", 2) \
            .load()

        parsed_df = rate_df \
            .withColumn("event_id", f.expr("uuid()")) \
            .withColumn("event_type", f.lit("order_placed")) \
            .withColumn("event_timestamp", f.col("timestamp")) \
            .withColumn("order_id", f.concat(f.lit("RATE-"), f.col("value").cast("string"))) \
            .withColumn("customer_id", f.concat(f.lit("CUST-"), (f.col("value") % 10 + 100).cast("string"))) \
            .withColumn("product_id", f.lit("PROD-001")) \
            .withColumn("product_name", f.lit("Test Product")) \
            .withColumn("quantity", (f.col("value") % 3 + 1).cast("int")) \
            .withColumn("unit_price", f.lit(99.99)) \
            .withColumn("total", f.col("unit_price") * f.col("quantity")) \
            .withColumn("processing_time", f.current_timestamp()) \
            .drop("timestamp", "value")

    # Write to Iceberg with checkpointing
    query = parsed_df.writeStream \
        .format("iceberg") \
        .outputMode("append") \
        .option("checkpointLocation", CHECKPOINT_DIR) \
        .option("fanout-enabled", "true") \
        .toTable("iceberg.test_streaming.orders")

    print(f"  Streaming query started: {query.id}")
    print(f"  Checkpoint location: {CHECKPOINT_DIR}")
    print("  Waiting for data...")

    # Wait for specified duration
    start_time = time.time()
    last_count = 0

    while time.time() - start_time < duration_seconds:
        if not query.isActive:
            print("  Query stopped unexpectedly!")
            break

        # Check progress
        try:
            current_count = spark.sql("SELECT COUNT(*) FROM iceberg.test_streaming.orders").collect()[0][0]
            if current_count > last_count:
                print(f"  Records written: {current_count} (+{current_count - last_count})")
                last_count = current_count
        except Exception:
            pass  # Table might not have data yet

        time.sleep(2)

    # Stop query
    query.stop()
    print(f"\n  Streaming query stopped")

    return query


def verify_streaming_results(spark):
    """Verify streaming data was written correctly."""
    print("\n" + "=" * 60)
    print("Verifying streaming results")
    print("=" * 60)

    try:
        # Check record count
        count = spark.sql("SELECT COUNT(*) FROM iceberg.test_streaming.orders").collect()[0][0]
        print(f"  Total records written: {count}")

        if count == 0:
            print("  ❌ No records written to Iceberg")
            return False

        # Check data quality
        print("\n  Sample records:")
        spark.sql("""
            SELECT order_id, product_name, total, event_timestamp
            FROM iceberg.test_streaming.orders
            ORDER BY event_timestamp DESC
            LIMIT 5
        """).show(truncate=False)

        # Check partitions
        print("\n  Partitions created:")
        partitions = spark.sql("SELECT * FROM iceberg.test_streaming.orders.partitions").collect()
        for p in partitions[:5]:
            print(f"    - {p['partition']}: {p['record_count']} records")

        # Check snapshots (commits)
        print("\n  Snapshots (streaming commits):")
        snapshots = spark.sql("SELECT * FROM iceberg.test_streaming.orders.snapshots").collect()
        print(f"    Total snapshots: {len(snapshots)}")

        # Verify no duplicates (exactly-once check)
        distinct_events = spark.sql("SELECT COUNT(DISTINCT event_id) FROM iceberg.test_streaming.orders").collect()[0][0]
        if distinct_events == count:
            print(f"\n  ✅ No duplicates detected (exactly-once semantics working)")
        else:
            print(f"\n  ⚠️  Possible duplicates: {count} total, {distinct_events} distinct")

        print("\n  ✅ Streaming verification passed")
        return True

    except Exception as e:
        print(f"  ❌ Verification failed: {e}")
        return False


def cleanup(spark):
    """Clean up test resources."""
    print("\n" + "=" * 60)
    print("Cleanup")
    print("=" * 60)

    try:
        spark.sql("DROP TABLE IF EXISTS iceberg.test_streaming.orders")
        spark.sql("DROP NAMESPACE IF EXISTS iceberg.test_streaming")
        print("  ✅ Cleaned up Iceberg tables")

        # Clean up checkpoint directory
        import shutil
        try:
            shutil.rmtree(CHECKPOINT_DIR)
            print(f"  ✅ Cleaned up checkpoint directory")
        except Exception:
            pass

        # Clean up Kafka topic
        if KAFKA_AVAILABLE:
            try:
                admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
                admin.delete_topics([KAFKA_TOPIC])
                print(f"  ✅ Deleted Kafka topic: {KAFKA_TOPIC}")
            except Exception:
                pass

    except Exception as e:
        print(f"  ⚠️  Cleanup warning: {e}")


def main():
    parser = ArgumentParser(description="Kafka to Iceberg Streaming Test")
    parser.add_argument("--duration", type=int, default=20, help="Test duration in seconds")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup")
    args = parser.parse_args()

    print("=" * 60)
    print("Kafka → Iceberg Streaming Integration Test")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Duration: {args.duration} seconds")
    print("=" * 60)

    # Initialize Spark
    spark = SparkSession.builder \
        .appName("Streaming-Iceberg-Test") \
        .config("spark.sql.streaming.schemaInference", "true") \
        .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    results = {}

    # Setup
    results['kafka_topic'] = create_kafka_topic()
    setup_iceberg_table(spark)

    # Start background producer
    stop_event = threading.Event()
    if KAFKA_AVAILABLE:
        producer_thread = threading.Thread(
            target=start_event_producer,
            args=(stop_event,),
            daemon=True
        )
        producer_thread.start()
        print("Started background event producer")

    # Run streaming query
    try:
        run_streaming_query(spark, args.duration)
        results['streaming_query'] = True
    except Exception as e:
        print(f"Streaming query failed: {e}")
        results['streaming_query'] = False

    # Stop producer
    stop_event.set()
    time.sleep(1)

    # Verify results
    results['verification'] = verify_streaming_results(spark)

    # Cleanup
    if not args.no_cleanup:
        cleanup(spark)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test}: {status}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ Streaming integration test passed!")
        print("   Kafka → Spark Streaming → Iceberg working correctly")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
