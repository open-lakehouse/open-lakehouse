"""Imperative medallion — the SAME bronze->silver->gold pipeline as the SDP
transformations/, written with traditional Spark.

This file is the CONTRAST artifact for the demo: put it next to the declarative
`transformations/*.py` to show what SDP removes. Note what you have to manage by
hand here that SDP infers/handles for you:

  - session creation + catalog/extension config
  - the execution ORDER (bronze must run before silver before gold)
  - every WRITE (target table, location, provider, mode) spelled out per table
  - no dependency graph, no automatic recompute, no built-in recovery

The declarative version expresses the same logic as functions that just RETURN a
DataFrame; SDP figures out the rest.
"""
from __future__ import annotations

import os

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

NS = os.environ.get("DEMO_NS", "")
WH = os.environ.get("MEDALLION_WAREHOUSE", "s3://lakehouse/warehouse/medallion")
ORDERS_PATH = os.environ.get("ORDERS_PATH", "/data/events/orders_7d.parquet")
DIMS_PATH = os.environ.get("DIMS_PATH", "/data/dimensions")
MAX_ROWS = int(os.environ.get("MEDALLION_MAX_ROWS", "500000"))

_ITEM = StructType(
    [
        StructField("item_id", IntegerType()),
        StructField("name", StringType()),
        StructField("price", DoubleType()),
        StructField("quantity", IntegerType()),
    ]
)
_BODY = StructType(
    [
        StructField("customer_lat", DoubleType()),
        StructField("customer_lon", DoubleType()),
        StructField("brand_id", IntegerType()),
        StructField("brand_name", StringType()),
        StructField("items", ArrayType(_ITEM)),
        StructField("total", DoubleType()),
    ]
)
_LIFECYCLE = [
    "order_created",
    "kitchen_started",
    "kitchen_finished",
    "order_ready",
    "driver_arrived",
    "driver_picked_up",
    "delivered",
]


def create_session() -> SparkSession:
    return (
        SparkSession.builder.appName("ImperativeMedallion")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
            "io.delta.sql.DeltaSparkSessionExtension",
        )
        .getOrCreate()
    )


def _write(df: DataFrame, schema: str, table: str) -> None:
    # Every table: spell out catalog target, Delta provider, managed location.
    (
        df.write.format("delta")
        .option("path", f"{WH}/{NS}{schema}/{table}")
        .mode("overwrite")
        .saveAsTable(f"unity.{NS}{schema}.{table}")
    )


def run(spark: SparkSession) -> None:
    # ---- BRONZE (must run first) ----
    orders = (
        spark.read.parquet(ORDERS_PATH)
        .limit(MAX_ROWS)
        .withColumn("event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " ")))
    )
    _write(orders, "bronze", "orders")
    dim_locations = spark.read.parquet(f"{DIMS_PATH}/locations.parquet")
    _write(dim_locations, "bronze", "dim_locations")

    # ---- SILVER (depends on bronze — you must read the written tables back) ----
    orders = spark.read.table(f"unity.{NS}bronze.orders").filter(
        f.col("event_id").isNotNull()
        & f.col("order_id").isNotNull()
        & f.col("event_timestamp").isNotNull()
    )
    enriched = (
        orders.withColumn("b", f.from_json("body", _BODY))
        .select(
            "event_id",
            "event_type",
            "event_timestamp",
            "order_id",
            "location_id",
            f.col("b.brand_id").alias("brand_id"),
            f.col("b.brand_name").alias("brand_name"),
            f.col("b.total").alias("order_total"),
            f.size("b.items").alias("num_items"),
        )
        .withColumns(
            {
                "event_hour": f.hour("event_timestamp"),
                "event_date": f.to_date("event_timestamp"),
            }
        )
    )
    loc = spark.read.table(f"unity.{NS}bronze.dim_locations").select(
        f.col("id").alias("location_id"), f.col("city").alias("city_name")
    )
    enriched = enriched.join(f.broadcast(loc), on="location_id", how="left")
    _write(enriched, "silver", "orders_enriched")

    lifecycle = (
        spark.read.table(f"unity.{NS}silver.orders_enriched")
        .filter(f.col("event_type").isin(_LIFECYCLE))
        .groupBy("order_id", "location_id", "city_name")
        .pivot("event_type", _LIFECYCLE)
        .agg(f.min("event_timestamp"))
        .withColumnsRenamed({"order_created": "created_at", "delivered": "delivered_at"})
        .withColumn(
            "total_min",
            (f.unix_timestamp("delivered_at") - f.unix_timestamp("created_at")) / 60,
        )
        .filter(f.col("delivered_at").isNotNull())
    )
    _write(lifecycle, "silver", "order_lifecycle")

    # ---- GOLD (depends on silver) ----
    brand_summary = (
        spark.read.table(f"unity.{NS}silver.orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("brand_id", "brand_name")
        .agg(
            f.count("order_id").alias("total_orders"),
            f.round(f.sum("order_total"), 2).alias("total_revenue"),
            f.round(f.avg("order_total"), 2).alias("avg_order_value"),
        )
        .orderBy(f.desc("total_revenue"))
    )
    _write(brand_summary, "gold", "brand_summary")

    hourly = (
        spark.read.table(f"unity.{NS}silver.orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("event_date", "event_hour", "location_id", "city_name")
        .agg(
            f.count("order_id").alias("order_count"),
            f.round(f.sum("order_total"), 2).alias("total_revenue"),
        )
    )
    _write(hourly, "gold", "hourly_metrics")


if __name__ == "__main__":
    spark = create_session()
    run(spark)
    spark.stop()
