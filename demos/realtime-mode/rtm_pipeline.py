"""Real-Time Mode (RTM) stateless guardrail pipeline.

Reads Ethereum-style block events from Kafka, applies stateless guardrail
checks (gas limits, transaction count anomalies, PII / credential patterns
in the free-text `extra_data` field), and dynamically routes each record
to either an `-allowed` or `-quarantine` output topic.

OSS Spark 4.1.0 ships `Trigger.RealTime(...)` as an `@Experimental` Scala API
(SPARK-52330 SPIP, SPARK-53736 stateless support landed in 4.1.0). There is
no native PySpark `trigger(realTime=...)` kwarg yet, so we reach through to
the JVM with `spark._jvm.org.apache.spark.sql.streaming.Trigger.RealTime(...)`
and call `writeStream._jwriter.trigger(...)`. Required output mode is
`update`; Kafka sink + stateless ops are on the OSS RTM allowlist.

Submit with spark-submit inside the spark-master-41 container:

    docker exec -d spark-master-41 /opt/spark/bin/spark-submit \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.0 \\
        /demos/realtime-mode/rtm_pipeline.py

Configuration is read from environment variables:

    KAFKA_BOOTSTRAP_SERVERS  default: kafka:9092
    INPUT_TOPIC              default: ethereum-blocks
    OUTPUT_TOPIC             default: ethereum-validated
    CHECKPOINT_DIR           default: /opt/spark-data/checkpoints/rtm-realtime-mode
    SHUFFLE_PARTITIONS       default: 8
    RTM_TRIGGER_INTERVAL     default: 5 seconds
    USE_REALTIME             default: 1 (set 0 to fall back to pure-Python
                              trigger(processingTime="0 seconds") — useful
                              if RTM is unavailable on the running cluster)
"""

from __future__ import annotations

import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = os.environ.get("INPUT_TOPIC", "ethereum-blocks")
OUTPUT_TOPIC = os.environ.get("OUTPUT_TOPIC", "ethereum-validated")
CHECKPOINT_DIR = os.environ.get(
    "CHECKPOINT_DIR", "/opt/spark-data/checkpoints/rtm-realtime-mode"
)
SHUFFLE_PARTITIONS = os.environ.get("SHUFFLE_PARTITIONS", "8")
RTM_TRIGGER_INTERVAL = os.environ.get("RTM_TRIGGER_INTERVAL", "5 seconds")
USE_REALTIME = os.environ.get("USE_REALTIME", "1") == "1"


BLOCK_SCHEMA = StructType(
    [
        StructField("block_number", LongType(), True),
        StructField("block_hash", StringType(), True),
        StructField("parent_hash", StringType(), True),
        StructField("miner", StringType(), True),
        StructField("gas_used", LongType(), True),
        StructField("gas_limit", LongType(), True),
        StructField("transaction_count", LongType(), True),
        StructField("timestamp", LongType(), True),
        StructField("total_value_wei", StringType(), True),
        StructField("extra_data", StringType(), True),
    ]
)


def detect_sensitive_data(col_name: str):
    """Return a Spark Column that classifies sensitive content in `col_name`.

    Uses native Spark SQL `rlike` to avoid Python UDF serialization overhead.
    Priority: credentials > PII > none.
    """
    return (
        f.when(
            f.col(col_name).rlike(r"AKIA[0-9A-Z]{16}"),
            f.lit("CREDENTIAL_AWS_KEY"),
        )
        .when(
            f.col(col_name).rlike(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
            f.lit("CREDENTIAL_JWT"),
        )
        .when(
            f.col(col_name).rlike(r"0x[a-fA-F0-9]{64}"),
            f.lit("CREDENTIAL_PRIVATE_KEY"),
        )
        .when(f.col(col_name).rlike(r"\b\d{3}-\d{2}-\d{4}\b"), f.lit("PII_SSN"))
        .when(
            f.col(col_name).rlike(r"\b(\d{4}[-\s]?){3}\d{4}\b"),
            f.lit("PII_CREDIT_CARD"),
        )
        .when(
            f.col(col_name).rlike(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"),
            f.lit("PII_EMAIL"),
        )
        .otherwise(None)
    )


VALIDATION_RULES = [
    ("gas_used > gas_limit * 0.95", "HIGH_GAS_USAGE"),
    ("transaction_count > 500", "HIGH_TX_COUNT"),
    ("transaction_count = 0", "EMPTY_BLOCK"),
    (
        "miner = '0x0000000000000000000000000000000000000000'",
        "ZERO_MINER",
    ),
]

SENSITIVE_COLUMNS = ["extra_data"]


def build_pipeline(spark: SparkSession):
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", INPUT_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = raw.select(
        f.col("timestamp").alias("kafka_timestamp"),
        f.col("key").cast("string").alias("kafka_key"),
        f.col("partition").alias("kafka_partition"),
        f.col("offset").alias("kafka_offset"),
        f.from_json(f.col("value").cast("string"), BLOCK_SCHEMA).alias("data"),
    ).select(
        "kafka_timestamp",
        "kafka_key",
        "kafka_partition",
        "kafka_offset",
        "data.*",
    )

    validated = parsed
    reason_columns: list[str] = []
    for condition, reason in VALIDATION_RULES:
        flag_col = f"_flag_{reason.lower()}"
        validated = validated.withColumn(
            flag_col,
            f.when(f.expr(condition), f.lit(reason)).otherwise(f.lit(None)),
        )
        reason_columns.append(flag_col)

    for col_name in SENSITIVE_COLUMNS:
        flag_col = f"_sensitive_{col_name}"
        validated = validated.withColumn(flag_col, detect_sensitive_data(col_name))
        reason_columns.append(flag_col)

    enriched = (
        validated.withColumn(
            "validation_reasons",
            f.expr(f"filter(array({','.join(reason_columns)}), x -> x is not null)"),
        )
        .withColumn("is_quarantined", f.size(f.col("validation_reasons")) > 0)
        .withColumn(
            "decision",
            f.when(f.col("is_quarantined"), f.lit("QUARANTINE")).otherwise(
                f.lit("ALLOW")
            ),
        )
        .withColumn("processed_at", f.current_timestamp())
    )

    with_topic = enriched.withColumn(
        "topic",
        f.when(
            f.col("is_quarantined"),
            f.lit(f"{OUTPUT_TOPIC}-quarantine"),
        ).otherwise(f.lit(f"{OUTPUT_TOPIC}-allowed")),
    )

    output_columns = [
        "block_number",
        "block_hash",
        "parent_hash",
        "miner",
        "gas_used",
        "gas_limit",
        "transaction_count",
        "timestamp",
        "total_value_wei",
        "decision",
        "is_quarantined",
        "validation_reasons",
        "processed_at",
        "kafka_timestamp",
    ]

    return with_topic.select(
        f.col("block_hash").cast("string").alias("key"),
        f.to_json(f.struct(*output_columns)).alias("value"),
        f.col("topic"),
    )


def main() -> int:
    spark = (
        SparkSession.builder.appName("rtm-realtime-mode")
        .config("spark.sql.shuffle.partitions", SHUFFLE_PARTITIONS)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print(f"input topic         : {INPUT_TOPIC}")
    print(f"output topic prefix : {OUTPUT_TOPIC} (-allowed, -quarantine)")
    print(f"bootstrap servers   : {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"checkpoint dir      : {CHECKPOINT_DIR}")
    print(
        "trigger             : "
        + (
            f"Trigger.RealTime('{RTM_TRIGGER_INTERVAL}') via JVM bridge"
            if USE_REALTIME
            else "processingTime='0 seconds' (RTM disabled)"
        )
    )

    output = build_pipeline(spark)

    writer = (
        output.writeStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("checkpointLocation", CHECKPOINT_DIR)
        .option("queryName", "rtm-realtime-mode")
        .outputMode("update")
    )

    if USE_REALTIME:
        # OSS Spark 4.1.0 — no native PySpark trigger(realTime=...) kwarg.
        # Reach into the JVM for Trigger.RealTime and apply it on the
        # underlying Java DataStreamWriter, then start through the Java side
        # too (the Python writer's _jwriter is now configured).
        jvm = spark._jvm
        rt_trigger = jvm.org.apache.spark.sql.streaming.Trigger.RealTime(
            RTM_TRIGGER_INTERVAL
        )
        j_writer = writer._jwriter.trigger(rt_trigger)
        j_query = j_writer.start()
        print(f"streaming query started: id={j_query.id()} name={j_query.name()}")
        j_query.awaitTermination()
    else:
        query = writer.trigger(processingTime="0 seconds").start()
        print(f"streaming query started: id={query.id} name={query.name}")
        query.awaitTermination()
    return 0


if __name__ == "__main__":
    sys.exit(main())
