"""The SAME medallion as the declarative SQL pipeline — written imperatively.

This file is a teaching artifact for the "imperative vs declarative" demo. Put
it next to transformations/*.sql and count what you have to manage by hand here
that SDP does for you:

  - create + configure the Spark session
  - the execution ORDER (bronze before silver before gold)
  - every read of an upstream table, threaded through as a variable
  - every WRITE: target table, format, catalog-managed property, mode
  - no dependency graph, no dry-run validation, no automatic recompute

The declarative version says the same thing in a few SQL `SELECT`s.
"""
from __future__ import annotations

import os

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

ORDERS_PATH = os.environ.get("ORDERS_PATH", "/data/events/orders_7d.parquet")
DIMS_PATH = os.environ.get("DIMS_PATH", "/data/dimensions")
CATALOG = os.environ.get("MANAGED_CATALOG", "managed_demo")
SCHEMA = os.environ.get("DEMO_NS", "medallion_demo").rstrip("_") or "medallion_demo"
MAX_ROWS = int(os.environ.get("MEDALLION_MAX_ROWS", "200000"))

_BODY = "struct<brand_id:int, brand_name:string, total:double, items:array<struct<quantity:int>>>"


def session() -> SparkSession:
    return SparkSession.builder.appName("imperative_medallion").getOrCreate()


def write(df: DataFrame, table: str) -> None:
    """Spell out the write for every table: target, provider, catalog-managed."""
    (
        df.writeTo(f"{CATALOG}.{SCHEMA}.{table}")
        .using("delta")
        .tableProperty("delta.feature.catalogManaged", "supported")
        .createOrReplace()
    )


def run(spark: SparkSession) -> None:
    # ---- BRONZE (must run first) ----
    orders_bronze = (
        spark.read.parquet(ORDERS_PATH)
        .limit(MAX_ROWS)
        .withColumn("event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " ")))
    )
    write(orders_bronze, "orders_bronze")
    write(spark.read.parquet(f"{DIMS_PATH}/locations.parquet"), "dim_locations")

    # ---- SILVER (depends on bronze — you must read the written tables back) ----
    bronze = spark.read.table(f"{CATALOG}.{SCHEMA}.orders_bronze")
    locations = spark.read.table(f"{CATALOG}.{SCHEMA}.dim_locations")
    parsed = bronze.withColumn("d", f.from_json("body", _BODY))
    orders_enriched = parsed.select(
        "event_id",
        "event_type",
        "event_timestamp",
        "order_id",
        "location_id",
        f.col("d.brand_id").alias("brand_id"),
        f.col("d.brand_name").alias("brand_name"),
        f.col("d.total").alias("order_total"),
        f.size("d.items").alias("num_items"),
        f.hour("event_timestamp").alias("event_hour"),
        f.to_date("event_timestamp").alias("event_date"),
    ).join(
        locations.select(f.col("id").alias("location_id"), f.col("city").alias("city_name")),
        on="location_id",
        how="left",
    )
    write(orders_enriched, "orders_enriched")

    # ---- GOLD (depends on silver) ----
    enriched = spark.read.table(f"{CATALOG}.{SCHEMA}.orders_enriched").where(
        "event_type = 'order_created'"
    )
    brand_summary = (
        enriched.groupBy("brand_name")
        .agg(
            f.count("*").alias("total_orders"),
            f.round(f.sum("order_total"), 2).alias("total_revenue"),
            f.round(f.avg("order_total"), 2).alias("avg_order_value"),
            f.countDistinct("location_id").alias("locations_served"),
        )
        .orderBy(f.desc("total_revenue"))
    )
    write(brand_summary, "gold_brand_summary")

    hourly = enriched.groupBy("event_date", "event_hour", "city_name").agg(
        f.count("*").alias("order_count"),
        f.round(f.sum("order_total"), 2).alias("total_revenue"),
        f.round(f.avg("order_total"), 2).alias("avg_order_value"),
    )
    write(hourly, "gold_hourly_metrics")


if __name__ == "__main__":
    spark = session()
    run(spark)
    spark.stop()
