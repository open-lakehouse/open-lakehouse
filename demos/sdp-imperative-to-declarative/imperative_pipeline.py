"""BEFORE — the same medallion pipeline written imperatively.

Run this against the Spark Connect server to see the imperative style: you
create the session, you read, you transform, you write each table, and you
order the steps by hand. Compare with declarative/ — same three tables, far
less ceremony, and SDP owns ordering + recovery.

Run:
    poetry run python demos/sdp-imperative-to-declarative/imperative_pipeline.py
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as f

# YOU manage the session.
remote = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
spark = SparkSession.builder.remote(remote).appName("imperative-medallion").getOrCreate()

# Step 1: bronze. YOU decide this runs first.
bronze = spark.range(200).selectExpr(
    "id AS order_id",
    "concat('cust_', cast(id % 25 AS STRING)) AS customer",
    "(id % 50) * 2.0 AS amount",
    "date_add(DATE '2026-05-01', cast(id % 7 AS INT)) AS order_date",
)
bronze.write.format("delta").mode("overwrite").saveAsTable(
    "spark_catalog.default.imp_orders_bronze"
)

# Step 2: silver. YOU must remember it depends on bronze, and run it after.
silver = (
    spark.read.table("spark_catalog.default.imp_orders_bronze")
    .where("amount > 0")
    .withColumn("_clean_ts", f.current_timestamp())
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
        f.sum("amount").alias("revenue"),
    )
)
gold.write.format("delta").mode("overwrite").saveAsTable(
    "spark_catalog.default.imp_orders_gold"
)

print("imperative run complete:")
for t in ("imp_orders_bronze", "imp_orders_silver", "imp_orders_gold"):
    n = spark.sql(f"SELECT count(*) c FROM spark_catalog.default.{t}").collect()[0]["c"]
    print(f"  spark_catalog.default.{t}: {n} rows")
