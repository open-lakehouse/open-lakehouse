"""Seed the Delta table that the streaming pipeline ingests from.

run.sh executes this once, before the pipeline. The seed is written as an
ordinary *batch* Delta table — that makes the demo deterministic: the
streaming table picks up exactly these rows on every run, with no dependence
on wall-clock timing (a `rate` source yields nothing under SDP's one-shot
trigger, since no time has elapsed when the run starts).
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as f

spark = SparkSession.builder.master("local[2]").appName("sxb-seed").getOrCreate()

(
    spark.range(300)
    .select(
        f.col("id").alias("event_id"),
        f.when(f.col("id") % 3 == 0, "click")
        .when(f.col("id") % 3 == 1, "view")
        .otherwise("purchase")
        .alias("event_type"),
        f.current_timestamp().alias("event_time"),
    )
    .write.format("delta")
    .mode("overwrite")
    .save("file:///tmp/sxb-seed")
)

spark.stop()
