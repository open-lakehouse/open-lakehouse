"""Seed the Delta table that the streaming pipeline ingests from.

run.sh executes this once, before the pipeline. It reads the generated event
dataset (`data/events/orders_7d.parquet`) — the order-lifecycle events, minus
the high-volume `driver_ping` GPS noise — and writes them as an ordinary
*batch* Delta table.

Writing the seed as a batch table (not a live stream) keeps the demo
deterministic: the streaming table picks up exactly these rows on every run.
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as f

spark = SparkSession.builder.master("local[2]").appName("sxb-seed").getOrCreate()

(
    spark.read.parquet("file:///data/events/orders_7d.parquet")
    .where("event_type != 'driver_ping'")
    .select(
        "event_id",
        "event_type",
        "order_id",
        f.to_timestamp("ts").alias("event_time"),
    )
    .write.format("delta")
    .mode("overwrite")
    .save("file:///tmp/sxb-seed")
)

spark.stop()
