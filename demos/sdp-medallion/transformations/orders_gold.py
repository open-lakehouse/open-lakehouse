"""Gold layer — business aggregations over the silver tables.

hourly_metrics: orders/revenue/AOV per hour and location.
delivery_performance: avg + p50/p95 kitchen & delivery times per day/location.
brand_summary: revenue/orders/AOV per brand.
"""
import os

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

NS = os.environ.get("DEMO_NS", "")

# Catalog-managed Delta: catalog assigns location; only provider + feature flag.
_PROPS = {"provider": "delta", "delta.feature.catalogManaged": "supported"}


def _sch(layer: str) -> str:
    return f"{NS}{layer}"


@dp.materialized_view(
    name=f"{_sch('gold')}.hourly_metrics",
    comment="Orders, revenue and AOV per hour and location.",
    table_properties=_PROPS,
)
def hourly_metrics() -> DataFrame:
    return (
        spark.read.table(f"{_sch('silver')}.orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("event_date", "event_hour", "location_id", "city_name")
        .agg(
            f.count("order_id").alias("order_count"),
            f.round(f.sum("order_total"), 2).alias("total_revenue"),
            f.round(f.avg("order_total"), 2).alias("avg_order_value"),
            f.countDistinct("brand_id").alias("unique_brands"),
        )
    )


@dp.materialized_view(
    name=f"{_sch('gold')}.delivery_performance",
    comment="Avg + p50/p95 kitchen and delivery times per day and location.",
    table_properties=_PROPS,
)
def delivery_performance() -> DataFrame:
    return (
        spark.read.table(f"{_sch('silver')}.order_lifecycle")
        .groupBy(
            f.to_date("created_at").alias("order_date"), "location_id", "city_name"
        )
        .agg(
            f.count("order_id").alias("completed_orders"),
            f.round(f.avg("kitchen_min"), 1).alias("avg_kitchen_min"),
            f.round(f.avg("delivery_min"), 1).alias("avg_delivery_min"),
            f.round(f.avg("total_min"), 1).alias("avg_total_min"),
            f.round(f.percentile_approx("total_min", 0.5), 1).alias("p50_total_min"),
            f.round(f.percentile_approx("total_min", 0.95), 1).alias("p95_total_min"),
        )
    )


@dp.materialized_view(
    name=f"{_sch('gold')}.brand_summary",
    comment="Revenue, orders and AOV per brand.",
    table_properties=_PROPS,
)
def brand_summary() -> DataFrame:
    return (
        spark.read.table(f"{_sch('silver')}.orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("brand_id", "brand_name")
        .agg(
            f.count("order_id").alias("total_orders"),
            f.round(f.sum("order_total"), 2).alias("total_revenue"),
            f.round(f.avg("order_total"), 2).alias("avg_order_value"),
            f.countDistinct("location_id").alias("locations_served"),
        )
        .orderBy(f.desc("total_revenue"))
    )
