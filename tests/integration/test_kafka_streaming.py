"""Integration tests for Kafka streaming pipelines.

Tests Kafka message production and consumption with Spark Structured Streaming.
"""

import json
import time

import pytest


@pytest.mark.integration
class TestKafkaConnectivity:
    """Test basic Kafka connectivity."""

    def test_kafka_container_running(self, kafka_container):
        """Verify Kafka container is running and accessible."""
        bootstrap_servers = kafka_container.get_bootstrap_server()
        assert bootstrap_servers is not None
        assert ":" in bootstrap_servers

    def test_create_topic(self, kafka_container):
        """Test creating a Kafka topic."""
        try:
            from kafka import KafkaAdminClient
            from kafka.admin import NewTopic
        except ImportError:
            pytest.skip("kafka-python not installed")

        bootstrap_servers = kafka_container.get_bootstrap_server()

        admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)

        topic_name = "test-topic-create"
        topic = NewTopic(name=topic_name, num_partitions=1, replication_factor=1)

        try:
            admin.create_topics([topic])
            topics = admin.list_topics()
            assert topic_name in topics
        finally:
            try:
                admin.delete_topics([topic_name])
            except Exception:
                pass
            admin.close()

    def test_produce_consume_message(self, kafka_container):
        """Test producing and consuming a message."""
        try:
            from kafka import KafkaConsumer, KafkaProducer
        except ImportError:
            pytest.skip("kafka-python not installed")

        bootstrap_servers = kafka_container.get_bootstrap_server()
        topic_name = "test-produce-consume"

        # Create producer
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        # Send message
        test_message = {"event": "test", "value": 42}
        producer.send(topic_name, test_message)
        producer.flush()
        producer.close()

        # Create consumer
        consumer = KafkaConsumer(
            topic_name,
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset="earliest",
            consumer_timeout_ms=10000,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        # Receive message
        messages = list(consumer)
        consumer.close()

        assert len(messages) >= 1
        assert messages[0].value == test_message


@pytest.mark.integration
@pytest.mark.slow
class TestSparkKafkaStreaming:
    """Test Spark Structured Streaming with Kafka."""

    @pytest.fixture
    def spark_with_kafka(self, kafka_container):
        """Create SparkSession configured for Kafka streaming."""
        from pyspark.sql import SparkSession

        bootstrap_servers = kafka_container.get_bootstrap_server()

        spark = (
            SparkSession.builder.appName("lakehouse-kafka-tests")
            .master("local[2]")
            .config("spark.driver.memory", "1g")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.ui.enabled", "false")
            .config(
                "spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.1",
            )
            .getOrCreate()
        )

        spark.sparkContext.setLogLevel("ERROR")
        yield spark, bootstrap_servers
        spark.stop()

    def test_read_kafka_batch(self, spark_with_kafka, kafka_container):
        """Test reading Kafka topic in batch mode."""
        try:
            from kafka import KafkaProducer
        except ImportError:
            pytest.skip("kafka-python not installed")

        spark, bootstrap_servers = spark_with_kafka
        topic_name = "test-spark-batch-read"

        # Produce some test messages
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        for i in range(5):
            producer.send(topic_name, {"id": i, "value": f"message-{i}"})
        producer.flush()
        producer.close()

        # Give Kafka time to persist
        time.sleep(2)

        # Read from Kafka using Spark
        df = (
            spark.read.format("kafka")
            .option("kafka.bootstrap.servers", bootstrap_servers)
            .option("subscribe", topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        # Parse value as JSON
        from pyspark.sql import functions as f

        parsed = df.select(
            f.from_json(
                f.col("value").cast("string"),
                "id INT, value STRING",
            ).alias("data")
        ).select("data.*")

        count = parsed.count()
        assert count >= 5

    def test_streaming_query_output(self, spark_with_kafka, kafka_container, tmp_path):
        """Test Spark Structured Streaming output."""
        try:
            from kafka import KafkaProducer
        except ImportError:
            pytest.skip("kafka-python not installed")

        spark, bootstrap_servers = spark_with_kafka
        topic_name = "test-spark-streaming"
        output_path = str(tmp_path / "streaming_output")

        # Produce test messages
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        for i in range(10):
            producer.send(topic_name, {"event_id": f"e{i}", "amount": i * 10})
        producer.flush()
        producer.close()

        time.sleep(2)

        # Start streaming query
        from pyspark.sql import functions as f

        stream_df = (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", bootstrap_servers)
            .option("subscribe", topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        parsed_stream = stream_df.select(
            f.from_json(
                f.col("value").cast("string"),
                "event_id STRING, amount INT",
            ).alias("data")
        ).select("data.*")

        # Write to parquet with checkpoint
        query = (
            parsed_stream.writeStream.format("parquet")
            .option("path", output_path)
            .option("checkpointLocation", str(tmp_path / "checkpoint"))
            .outputMode("append")
            .trigger(once=True)
            .start()
        )

        # Wait for completion
        query.awaitTermination(timeout=60)

        # Verify output
        result = spark.read.parquet(output_path)
        assert result.count() >= 10


@pytest.mark.integration
class TestKafkaIcebergPipeline:
    """Test end-to-end Kafka to Iceberg pipeline."""

    @pytest.mark.slow
    def test_kafka_to_iceberg_flow(self, spark_local, kafka_container):
        """Test streaming data from Kafka to Iceberg table."""
        try:
            from kafka import KafkaProducer
        except ImportError:
            pytest.skip("kafka-python not installed")

        spark = spark_local
        bootstrap_servers = kafka_container.get_bootstrap_server()
        topic_name = "test-kafka-iceberg"

        # Setup Iceberg table
        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.streaming")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.streaming.events (
                event_id STRING,
                event_type STRING,
                amount DOUBLE,
                processed_at TIMESTAMP
            )
            USING iceberg
        """)

        # Produce test events
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        events = [
            {"event_id": "e1", "event_type": "purchase", "amount": 99.99},
            {"event_id": "e2", "event_type": "refund", "amount": 49.99},
            {"event_id": "e3", "event_type": "purchase", "amount": 149.99},
        ]

        for event in events:
            producer.send(topic_name, event)
        producer.flush()
        producer.close()

        time.sleep(2)

        # Read batch from Kafka and write to Iceberg
        from pyspark.sql import functions as f

        kafka_df = (
            spark.read.format("kafka")
            .option("kafka.bootstrap.servers", bootstrap_servers)
            .option("subscribe", topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        parsed = kafka_df.select(
            f.from_json(
                f.col("value").cast("string"),
                "event_id STRING, event_type STRING, amount DOUBLE",
            ).alias("data")
        ).select("data.*")

        # Add processing timestamp and write to Iceberg
        with_timestamp = parsed.withColumn("processed_at", f.current_timestamp())
        with_timestamp.writeTo("iceberg.streaming.events").append()

        # Verify data in Iceberg
        result = spark.sql(
            "SELECT COUNT(*) as cnt FROM iceberg.streaming.events"
        ).collect()[0]
        assert result.cnt >= 3

        # Verify aggregations work
        total = spark.sql("""
            SELECT SUM(amount) as total
            FROM iceberg.streaming.events
            WHERE event_type = 'purchase'
        """).collect()[0]
        assert abs(total.total - 249.98) < 0.01
