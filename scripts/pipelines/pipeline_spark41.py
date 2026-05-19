#!/usr/bin/env python3
"""
Spark 4.1 Declarative Pipeline
==============================

Pipeline using decorator-based approach that mimics Spark Declarative Pipelines (SDP).
Functions define WHAT tables contain, not HOW to execute them.

Key differences from imperative:
  - Functions only RETURN DataFrames (no write statements)
  - Dependencies inferred from spark.table() calls
  - Execution order determined automatically
  - Single run() call executes everything

Usage:
    # On Spark 4.1 cluster
    docker exec spark-master-41 /opt/spark/bin/spark-submit /scripts/pipeline_spark41.py

Note: In production with actual SDP, you would use:
    spark-pipelines run --spec scripts/spark-pipeline.yml
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    DoubleType,
)
from functools import wraps
from typing import Callable, Dict, List, Set
import re


# =============================================================================
# PIPELINE FRAMEWORK (Mimics SDP)
# =============================================================================

class Pipeline:
    """Mini SDP framework that demonstrates declarative pipeline patterns.

    In production, you'd use: from pyspark import pipelines as dp
    """

    def __init__(self, name: str, catalog: str = "iceberg"):
        self.name = name
        self.catalog = catalog
        self.tables: Dict[str, dict] = {}
        self._spark: SparkSession = None

    @property
    def spark(self) -> SparkSession:
        if self._spark is None:
            self._spark = SparkSession.builder \
                .appName(f"Pipeline_{self.name}") \
                .getOrCreate()
            self._spark.sparkContext.setLogLevel("WARN")
        return self._spark

    def materialized_view(self, name: str, layer: str = "bronze"):
        """Decorator that registers a table definition."""
        def decorator(func: Callable):
            # Infer dependencies from spark.table() calls
            import inspect
            source = inspect.getsource(func)
            deps = set(re.findall(r'spark\.table\(["\']([^"\']+)["\']\)', source))

            self.tables[name] = {
                'func': func,
                'layer': layer,
                'deps': deps,
            }

            @wraps(func)
            def wrapper():
                return func()
            return wrapper
        return decorator

    def _get_execution_order(self) -> List[str]:
        """Topologically sort tables based on dependencies."""
        visited: Set[str] = set()
        order: List[str] = []

        def visit(table_name: str):
            if table_name in visited:
                return
            visited.add(table_name)

            if table_name in self.tables:
                for dep in self.tables[table_name]['deps']:
                    short_dep = dep.replace(f"{self.catalog}.", "")
                    visit(short_dep)
            order.append(table_name)

        for table_name in self.tables:
            visit(table_name)

        return order

    def run(self, layer: str = None) -> Dict[str, int]:
        """Execute the pipeline."""
        results = {}
        order = self._get_execution_order()

        print(f"\nSpark Version: {self.spark.version}")
        print("=" * 60)
        print("DECLARATIVE PIPELINE (Spark 4.1 Style)")
        print("=" * 60)
        print(f"\nExecution order (auto-resolved): {order}")

        for table_name in order:
            if table_name not in self.tables:
                continue

            info = self.tables[table_name]
            if layer and info['layer'] != layer:
                continue

            full_name = f"{self.catalog}.{table_name}"
            deps = info['deps']

            layer_name = info['layer'].upper()
            print(f"\n[{layer_name}] {table_name}")
            if deps:
                print(f"  Dependencies: {deps}")

            # Execute and write
            df = info['func']()
            df.write.mode("overwrite").saveAsTable(full_name)

            # Get count from table (avoids re-scan of large DataFrames)
            count = self.spark.sql(f"SELECT COUNT(*) as cnt FROM {full_name}").collect()[0]['cnt']
            results[table_name] = count
            print(f"  -> {count:,} rows")

        print("\n" + "=" * 60)
        print(f"Pipeline complete: {len(results)} tables created")
        print("=" * 60)

        return results

    def stop(self):
        if self._spark:
            self._spark.stop()


# Create pipeline instance
pipeline = Pipeline("lakehouse_pipeline", catalog="iceberg")
spark = pipeline.spark  # Global spark for table functions


# =============================================================================
# BRONZE LAYER - Raw Data Ingestion
# =============================================================================

@pipeline.materialized_view(name="bronze.dim_categories", layer="bronze")
def dim_categories():
    """Food categories dimension table."""
    return spark.read.parquet("/data/dimensions/categories.parquet")


@pipeline.materialized_view(name="bronze.dim_brands", layer="bronze")
def dim_brands():
    """Ghost kitchen brands dimension table."""
    return spark.read.parquet("/data/dimensions/brands.parquet")


@pipeline.materialized_view(name="bronze.dim_items", layer="bronze")
def dim_items():
    """Menu items dimension table."""
    return spark.read.parquet("/data/dimensions/items.parquet")


@pipeline.materialized_view(name="bronze.dim_locations", layer="bronze")
def dim_locations():
    """Delivery locations dimension table."""
    return spark.read.parquet("/data/dimensions/locations.parquet")


@pipeline.materialized_view(name="bronze.orders", layer="bronze")
def orders_batch():
    """Order lifecycle events with timestamp parsing."""
    df = spark.read.parquet("/data/events/orders_90d.parquet")
    return df.withColumn(
        "event_timestamp",
        f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


# =============================================================================
# SILVER LAYER - Cleaned and Enriched
# =============================================================================

@pipeline.materialized_view(name="silver.orders_enriched", layer="silver")
def orders_enriched():
    """Orders with parsed JSON body, time features, and location join.

    Dependencies auto-inferred from spark.table() calls below.
    """
    orders = spark.table("iceberg.bronze.orders")
    locations = spark.table("iceberg.bronze.dim_locations")

    # Filter nulls
    cleaned = orders.filter(
        f.col("event_id").isNotNull() &
        f.col("order_id").isNotNull() &
        f.col("event_timestamp").isNotNull()
    )

    # Parse JSON body
    body_schema = StructType([
        StructField("brand_id", IntegerType(), True),
        StructField("item_ids", StringType(), True),
        StructField("total", DoubleType(), True),
        StructField("lat", DoubleType(), True),
        StructField("lng", DoubleType(), True),
        StructField("driver_id", StringType(), True),
    ])

    enriched = cleaned.withColumn("body_parsed", f.from_json("body", body_schema))

    # Extract fields
    enriched = enriched.select(
        "event_id", "event_type", "event_timestamp", "ts", "ts_seconds",
        "order_id", "location_id", "sequence", "body",
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
    locations_lookup = locations.select(
        f.col("id").alias("location_id"),
        f.col("city").alias("city_name"),
    )

    return enriched.join(f.broadcast(locations_lookup), on="location_id", how="left")


@pipeline.materialized_view(name="silver.order_lifecycle", layer="silver")
def order_lifecycle():
    """Pivoted view with one row per completed order and duration metrics."""
    orders = spark.table("iceberg.silver.orders_enriched")

    # Pivot events to columns
    lifecycle = orders.groupBy("order_id", "location_id", "city_name").pivot(
        "event_type",
        ["order_created", "kitchen_started", "kitchen_finished", "order_ready",
         "driver_arrived", "driver_picked_up", "delivered"]
    ).agg(f.min("event_timestamp").alias("ts"))

    # Rename columns
    lifecycle = lifecycle.select(
        "order_id", "location_id", "city_name",
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
        "kitchen_duration_min": (f.unix_timestamp("kitchen_finished_at") - f.unix_timestamp("kitchen_started_at")) / 60,
        "delivery_duration_min": (f.unix_timestamp("delivered_at") - f.unix_timestamp("pickup_at")) / 60,
        "total_duration_min": (f.unix_timestamp("delivered_at") - f.unix_timestamp("created_at")) / 60,
    })

    # Filter to completed orders
    return lifecycle.filter(f.col("delivered_at").isNotNull())


# =============================================================================
# GOLD LAYER - Business Aggregations
# =============================================================================

@pipeline.materialized_view(name="gold.hourly_metrics", layer="gold")
def hourly_metrics():
    """Hourly order metrics by location."""
    orders = spark.table("iceberg.silver.orders_enriched")

    return orders.filter(f.col("event_type") == "order_created").groupBy(
        "event_date", "event_hour", "location_id", "city_name"
    ).agg(
        f.count("order_id").alias("order_count"),
        f.sum("order_total").alias("total_revenue"),
        f.avg("order_total").alias("avg_order_value"),
        f.countDistinct("brand_id").alias("unique_brands"),
    )


@pipeline.materialized_view(name="gold.delivery_performance", layer="gold")
def delivery_performance():
    """Delivery performance metrics by date and location."""
    lifecycle = spark.table("iceberg.silver.order_lifecycle")

    return lifecycle.groupBy(
        f.to_date("created_at").alias("order_date"),
        "location_id", "city_name"
    ).agg(
        f.count("order_id").alias("completed_orders"),
        f.avg("kitchen_duration_min").alias("avg_kitchen_time_min"),
        f.avg("delivery_duration_min").alias("avg_delivery_time_min"),
        f.avg("total_duration_min").alias("avg_total_time_min"),
        f.percentile_approx("total_duration_min", 0.5).alias("median_total_time_min"),
        f.percentile_approx("total_duration_min", 0.95).alias("p95_total_time_min"),
    )


@pipeline.materialized_view(name="gold.brand_summary", layer="gold")
def brand_summary():
    """Brand-level summary metrics."""
    orders = spark.table("iceberg.silver.orders_enriched")
    brands = spark.table("iceberg.bronze.dim_brands")

    brand_metrics = orders.filter(f.col("event_type") == "order_created").groupBy("brand_id").agg(
        f.count("order_id").alias("total_orders"),
        f.sum("order_total").alias("total_revenue"),
        f.avg("order_total").alias("avg_order_value"),
        f.countDistinct("location_id").alias("locations_served"),
        f.min("event_date").alias("first_order_date"),
        f.max("event_date").alias("last_order_date"),
    )

    return brand_metrics.join(
        brands.select(f.col("id").alias("brand_id"), "name"),
        on="brand_id", how="left"
    ).select(
        "brand_id", f.col("name").alias("brand_name"),
        "total_orders", "total_revenue", "avg_order_value",
        "locations_served", "first_order_date", "last_order_date",
    )


# =============================================================================
# PIPELINE EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Single call runs everything in correct order
    results = pipeline.run()
    pipeline.stop()
