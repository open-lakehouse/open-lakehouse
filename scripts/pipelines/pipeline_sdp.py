"""Lakehouse Pipeline using Spark Declarative Pipelines (SDP).

This pipeline uses the official Spark 4.1.0 Declarative Pipelines API
to implement a medallion architecture for order processing.

Usage:
    # Run full pipeline
    spark-pipelines run --spec scripts/spark-pipeline.yml

    # Validate without running
    spark-pipelines dry-run --spec scripts/spark-pipeline.yml

Layers:
    - Bronze: Raw data ingestion from parquet and Kafka
    - Silver: Cleaned and enriched data
    - Gold: Business-ready aggregations
"""

from typing import Any

from pyspark import pipelines as dp
from pyspark.sql import functions as f
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    DoubleType,
)

# spark is injected by the Spark Declarative Pipelines framework at runtime
spark: Any


# =============================================================================
# BRONZE LAYER - Raw Data Ingestion
# =============================================================================


@dp.materialized_view(name="bronze.dim_categories")
def dim_categories():
    """Food categories dimension table."""
    return spark.read.parquet("/data/dimensions/categories.parquet")


@dp.materialized_view(name="bronze.dim_brands")
def dim_brands():
    """Ghost kitchen brands dimension table."""
    return spark.read.parquet("/data/dimensions/brands.parquet")


@dp.materialized_view(name="bronze.dim_items")
def dim_items():
    """Menu items dimension table."""
    return spark.read.parquet("/data/dimensions/items.parquet")


@dp.materialized_view(name="bronze.dim_locations")
def dim_locations():
    """Delivery locations dimension table."""
    return spark.read.parquet("/data/dimensions/locations.parquet")


@dp.materialized_view(name="bronze.orders")
def orders_batch():
    """Order lifecycle events from batch parquet source."""
    df = spark.read.parquet("/data/events/orders_90d.parquet")
    return df.withColumn(
        "event_timestamp",
        f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


# Streaming table for Kafka ingestion
@dp.table(name="bronze.orders_streaming")
def orders_streaming():
    """Order lifecycle events from Kafka stream."""
    event_schema = StructType([
        StructField("event_id", StringType()),
        StructField("event_type", StringType()),
        StructField("ts", StringType()),
        StructField("ts_seconds", IntegerType()),
        StructField("order_id", StringType()),
        StructField("location_id", IntegerType()),
        StructField("sequence", IntegerType()),
        StructField("body", StringType()),
    ])

    kafka_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", "localhost:9092")
        .option("subscribe", "orders")
        .option("startingOffsets", "latest")
        .load()
    )

    parsed = kafka_df.select(
        f.from_json(f.col("value").cast("string"), event_schema).alias("event"),
        f.col("timestamp").alias("kafka_timestamp"),
    ).select(
        "event.*",
        "kafka_timestamp",
    )

    return parsed.withColumn(
        "event_timestamp",
        f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


# =============================================================================
# SILVER LAYER - Cleaned & Enriched Data
# =============================================================================


@dp.materialized_view(name="silver.orders_enriched")
def orders_enriched():
    """Orders with parsed JSON body, time features, and location join.

    Transformations:
    - Filter null event_ids and order_ids
    - Parse JSON body to extract brand_id, total, coordinates, driver_id
    - Add time-based features (hour, day_of_week, is_weekend)
    - Join with locations for city name
    """
    orders = spark.table("iceberg.bronze.orders")

    # Filter nulls
    cleaned = orders.filter(
        f.col("event_id").isNotNull() &
        f.col("order_id").isNotNull() &
        f.col("event_timestamp").isNotNull()
    )

    # Parse JSON body
    body_schema = StructType([
        StructField("brand_id", IntegerType()),
        StructField("item_ids", StringType()),
        StructField("total", DoubleType()),
        StructField("lat", DoubleType()),
        StructField("lng", DoubleType()),
        StructField("driver_id", StringType()),
    ])

    enriched = cleaned.withColumn("body_parsed", f.from_json("body", body_schema))

    # Extract fields
    enriched = enriched.select(
        "event_id",
        "event_type",
        "event_timestamp",
        "ts",
        "ts_seconds",
        "order_id",
        "location_id",
        "sequence",
        "body",
        f.col("body_parsed.brand_id").alias("brand_id"),
        f.col("body_parsed.total").alias("order_total"),
        f.col("body_parsed.lat").alias("latitude"),
        f.col("body_parsed.lng").alias("longitude"),
        f.col("body_parsed.driver_id").alias("driver_id"),
    )

    # Add time features
    enriched = enriched.withColumns({
        "event_hour": f.hour("event_timestamp"),
        "event_day_of_week": f.dayofweek("event_timestamp"),
        "is_weekend": f.when(f.dayofweek("event_timestamp").isin(1, 7), True).otherwise(False),
        "event_date": f.to_date("event_timestamp"),
    })

    # Join with locations
    locations = spark.table("iceberg.bronze.dim_locations").select(
        f.col("id").alias("location_id"),
        f.col("city").alias("city_name"),
    )

    return enriched.join(f.broadcast(locations), on="location_id", how="left")


@dp.materialized_view(name="silver.order_lifecycle")
def order_lifecycle():
    """Pivoted view with one row per completed order and duration metrics.

    Output columns:
    - order_id, location_id, city_name
    - Timestamps: created_at, kitchen_started_at, ..., delivered_at
    - Durations: kitchen_duration_min, delivery_duration_min, total_duration_min
    """
    orders = spark.table("iceberg.silver.orders_enriched")

    # Pivot to get one row per order with timestamps for each event type
    lifecycle = orders.groupBy("order_id", "location_id", "city_name").pivot(
        "event_type",
        ["order_created", "kitchen_started", "kitchen_finished", "order_ready",
         "driver_arrived", "driver_picked_up", "delivered"]
    ).agg(f.min("event_timestamp").alias("ts"))

    # Rename columns
    lifecycle = lifecycle.select(
        "order_id",
        "location_id",
        "city_name",
        f.col("order_created").alias("created_at"),
        f.col("kitchen_started").alias("kitchen_started_at"),
        f.col("kitchen_finished").alias("kitchen_finished_at"),
        f.col("order_ready").alias("order_ready_at"),
        f.col("driver_arrived").alias("driver_arrived_at"),
        f.col("driver_picked_up").alias("pickup_at"),
        f.col("delivered").alias("delivered_at"),
    )

    # Calculate durations
    lifecycle = lifecycle.withColumns({
        "kitchen_duration_min": (
            f.unix_timestamp("kitchen_finished_at") - f.unix_timestamp("kitchen_started_at")
        ) / 60,
        "delivery_duration_min": (
            f.unix_timestamp("delivered_at") - f.unix_timestamp("pickup_at")
        ) / 60,
        "total_duration_min": (
            f.unix_timestamp("delivered_at") - f.unix_timestamp("created_at")
        ) / 60,
    })

    # Only completed orders
    return lifecycle.filter(f.col("delivered_at").isNotNull())


# =============================================================================
# GOLD LAYER - Business Aggregations
# =============================================================================


@dp.materialized_view(name="gold.hourly_metrics")
def hourly_metrics():
    """Hourly order metrics by location.

    Metrics: order_count, total_revenue, avg_order_value, unique_brands
    """
    orders = spark.table("iceberg.silver.orders_enriched")

    return orders.filter(
        f.col("event_type") == "order_created"
    ).groupBy(
        "event_date",
        "event_hour",
        "location_id",
        "city_name",
    ).agg(
        f.count("order_id").alias("order_count"),
        f.sum("order_total").alias("total_revenue"),
        f.avg("order_total").alias("avg_order_value"),
        f.countDistinct("brand_id").alias("unique_brands"),
    )


@dp.materialized_view(name="gold.delivery_performance")
def delivery_performance():
    """Delivery performance metrics by date and location.

    Metrics: completed_orders, avg/median/p95 times for kitchen, delivery, total
    """
    lifecycle = spark.table("iceberg.silver.order_lifecycle")

    return lifecycle.groupBy(
        f.to_date("created_at").alias("order_date"),
        "location_id",
        "city_name",
    ).agg(
        f.count("order_id").alias("completed_orders"),
        f.avg("kitchen_duration_min").alias("avg_kitchen_time_min"),
        f.avg("delivery_duration_min").alias("avg_delivery_time_min"),
        f.avg("total_duration_min").alias("avg_total_time_min"),
        f.percentile_approx("total_duration_min", 0.5).alias("median_total_time_min"),
        f.percentile_approx("total_duration_min", 0.95).alias("p95_total_time_min"),
    )


@dp.materialized_view(name="gold.brand_summary")
def brand_summary():
    """Brand-level summary metrics.

    Metrics: total_orders, total_revenue, avg_order_value, locations_served, date range
    """
    orders = spark.table("iceberg.silver.orders_enriched")
    brands = spark.table("iceberg.bronze.dim_brands")

    brand_metrics = orders.filter(
        f.col("event_type") == "order_created"
    ).groupBy("brand_id").agg(
        f.count("order_id").alias("total_orders"),
        f.sum("order_total").alias("total_revenue"),
        f.avg("order_total").alias("avg_order_value"),
        f.countDistinct("location_id").alias("locations_served"),
        f.min("event_date").alias("first_order_date"),
        f.max("event_date").alias("last_order_date"),
    )

    return brand_metrics.join(
        brands.select(f.col("id").alias("brand_id"), "name"),
        on="brand_id",
        how="left"
    ).select(
        "brand_id",
        f.col("name").alias("brand_name"),
        "total_orders",
        "total_revenue",
        "avg_order_value",
        "locations_served",
        "first_order_date",
        "last_order_date",
    )
