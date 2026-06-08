"""Real-Time Mode demo helpers — Kafka source -> guardrails -> live sink.

The whole point of the demo: enabling Real-Time Mode is a ONE-LINE change.
`start_query(spark, use_realtime=False)` uses a normal micro-batch trigger;
`start_query(spark, use_realtime=True)` swaps in Spark 4.1's `Trigger.RealTime`
via the JVM (there's no native PySpark kwarg for it yet).

Validated facts (Spark 4.1.0):
  - RTM minimum trigger interval is 5000 ms (realTimeMode.minBatchDuration).
  - A console/memory sink needs spark.sql.streaming.realTimeMode.allowlistCheck=false.
  - RTM REQUIRES a Kafka source — rate/file sources are not supported.
"""
from __future__ import annotations

import json
import random
import threading
import time

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

TOPIC = "rtm-orders"
BOOTSTRAP = "localhost:9092"
RTM_INTERVAL = "5 seconds"  # must be >= realTimeMode.minBatchDuration (5000 ms)

SCHEMA = StructType(
    [
        StructField("order_id", StringType()),
        StructField("brand", StringType()),
        StructField("total", DoubleType()),
        StructField("num_items", IntegerType()),
        StructField("note", StringType()),
    ]
)

_BRANDS = ["Pizza Planet", "Ramen House", "Pho Real", "Wok This Way", "Curry House"]
_AWS_KEY_RE = r"AKIA[0-9A-Z]{16}"


def guardrail(df: DataFrame) -> DataFrame:
    """Stateless guardrail checks → reasons[] + ALLOW/QUARANTINE decision."""
    return (
        df.withColumn(
            "reasons",
            f.array_compact(
                f.array(
                    f.when(f.col("total") > 200, f.lit("HIGH_TOTAL")),
                    f.when(f.col("num_items") > 7, f.lit("TOO_MANY_ITEMS")),
                    f.when(f.col("note").rlike(_AWS_KEY_RE), f.lit("LEAKED_SECRET")),
                )
            ),
        ).withColumn(
            "decision",
            f.when(f.size("reasons") > 0, f.lit("QUARANTINE")).otherwise(f.lit("ALLOW")),
        )
    )


def start_query(
    spark: SparkSession,
    use_realtime: bool,
    query_name: str = "decisions",
    bootstrap: str = BOOTSTRAP,
    topic: str = TOPIC,
):
    """Build the kafka -> guardrail -> in-memory stream and start it.

    Writes to an in-memory table (queryable live as `query_name`) so a notebook
    can display a clean, growing table of decisions. The ONLY difference RTM
    makes is the trigger — see the if/else at the bottom.
    """
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", "latest")
        .load()
    )
    parsed = raw.select(
        f.from_json(f.col("value").cast("string"), SCHEMA).alias("d")
    ).select("d.*")
    guarded = guardrail(parsed).select(
        "order_id", "brand", "total", "decision", "reasons"
    )
    writer = (
        guarded.writeStream.format("memory").queryName(query_name).outputMode("update")
    )

    # ── the one-line change ──────────────────────────────────────────────────
    if use_realtime:
        rt = spark._jvm.org.apache.spark.sql.streaming.Trigger.RealTime(RTM_INTERVAL)
        return writer._jwrite.trigger(rt).start()       # Real-Time Mode
    return writer.trigger(processingTime=RTM_INTERVAL).start()  # micro-batch
    # ─────────────────────────────────────────────────────────────────────────


def start_producer(
    bootstrap: str = BOOTSTRAP, topic: str = TOPIC, rows_per_sec: int = 20
) -> threading.Thread:
    """Drip synthetic order events into Kafka on a daemon thread (for the demo)."""
    from kafka import KafkaProducer

    def _run():
        p = KafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        i = 0
        while True:
            p.send(
                topic,
                {
                    "order_id": f"O{i:06d}",
                    "brand": random.choice(_BRANDS),
                    "total": round(random.uniform(8, 240), 2),
                    "num_items": random.randint(1, 9),
                    # occasionally leak a credential to trip the guardrail
                    "note": "AKIAIOSFODNN7EXAMPLE" if i % 23 == 0 else "ok",
                },
            )
            i += 1
            time.sleep(1.0 / max(rows_per_sec, 1))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
