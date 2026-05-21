"""BEFORE — the same medallion pipeline written imperatively.

Run this against the Spark Connect server to see the imperative style: you
create the session, you read, you transform, you write each table, and you
order the steps by hand. Compare with declarative/ — same three tables, far
less ceremony, and SDP owns ordering + recovery.

Source: the generated order-event dataset (`data/events/orders_7d.parquet`).

Run:
    poetry run python demos/sdp-imperative-to-declarative/imperative_pipeline.py
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as f

# YOU manage the session.
remote = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
spark = SparkSession.builder.remote(remote).appName("imperative-medallion").getOrCreate()

# Schema of the JSON `body` column in the raw event feed.
BODY = (
    "customer_lat DOUBLE, customer_lon DOUBLE, brand_id BIGINT, "
    "brand_name STRING, "
    "items ARRAY<STRUCT<item_id BIGINT, name STRING, price DOUBLE, quantity BIGINT>>, "
    "total DOUBLE"
)

# Step 1: bronze. YOU decide this runs first.
bronze = (
    spark.read.parquet("file:///data/events/orders_7d.parquet")
    .where("event_type = 'order_created'")
    .withColumn("o", f.from_json("body", BODY))
    .select(
        "order_id",
        f.to_timestamp("ts").alias("order_ts"),
        "location_id",
        f.col("o.brand_name").alias("brand"),
        f.col("o.total").alias("order_total"),
        f.size("o.items").alias("item_count"),
    )
)
bronze.write.format("delta").mode("overwrite").saveAsTable(
    "spark_catalog.default.imp_orders_bronze"
)

# Step 2: silver. YOU must remember it depends on bronze, and run it after.
silver = (
    spark.read.table("spark_catalog.default.imp_orders_bronze")
    .where("order_total > 0")
    .withColumn("order_date", f.to_date("order_ts"))
)
silver.write.format("delta").mode("overwrite").saveAsTable(
    "spark_catalog.default.imp_orders_silver"
)

# Step 3: gold. YOU must run it last, after silver.
gold = (
    spark.read.table("spark_catalog.default.imp_orders_silver")
    .groupBy("order_date")
    .agg(
        f.count("*").alias("order_count"),
        f.round(f.sum("order_total"), 2).alias("revenue"),
    )
)
gold.write.format("delta").mode("overwrite").saveAsTable(
    "spark_catalog.default.imp_orders_gold"
)

print("imperative run complete:")
for t in ("imp_orders_bronze", "imp_orders_silver", "imp_orders_gold"):
    n = spark.sql(f"SELECT count(*) c FROM spark_catalog.default.{t}").collect()[0]["c"]
    print(f"  spark_catalog.default.{t}: {n} rows")
