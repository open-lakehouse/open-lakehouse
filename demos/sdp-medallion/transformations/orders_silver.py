"""Silver layer — enriched events and per-order lifecycle.

`orders_enriched` parses the JSON `body` (real schema: customer geo, brand,
line items, total), adds time features, and joins the location dimension for the
city name. `order_lifecycle` pivots the per-order event stream into one row with
kitchen + delivery durations.
"""
import os

from pyspark import pipelines as dp
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

spark = SparkSession.active()

NS = os.environ.get("DEMO_NS", "")

# Catalog-managed Delta: catalog assigns location; only provider + feature flag.
_PROPS = {"provider": "delta", "delta.feature.catalogManaged": "supported"}


def _sch(layer: str) -> str:
    return f"{NS}{layer}"


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


@dp.materialized_view(
    name=f"{_sch('silver')}.orders_enriched",
    comment="Events with parsed body, item counts, time features, city join.",
    table_properties=_PROPS,
)
def orders_enriched() -> DataFrame:
    orders = spark.read.table(f"{_sch('bronze')}.orders").filter(
        f.col("event_id").isNotNull()
        & f.col("order_id").isNotNull()
        & f.col("event_timestamp").isNotNull()
    )
    parsed = (
        orders.withColumn("b", f.from_json("body", _BODY))
        .select(
            "event_id",
            "event_type",
            "event_timestamp",
            "ts_seconds",
            "order_id",
            "location_id",
            "sequence",
            f.col("b.brand_id").alias("brand_id"),
            f.col("b.brand_name").alias("brand_name"),
            f.col("b.total").alias("order_total"),
            f.col("b.customer_lat").alias("latitude"),
            f.col("b.customer_lon").alias("longitude"),
            f.size("b.items").alias("num_items"),
            f.aggregate(
                "b.items", f.lit(0), lambda acc, x: acc + x["quantity"]
            ).alias("total_quantity"),
        )
        .withColumns(
            {
                "event_hour": f.hour("event_timestamp"),
                "event_dow": f.dayofweek("event_timestamp"),
                "is_weekend": f.dayofweek("event_timestamp").isin(1, 7),
                "event_date": f.to_date("event_timestamp"),
            }
        )
    )
    loc = spark.read.table(f"{_sch('bronze')}.dim_locations").select(
        f.col("id").alias("location_id"), f.col("city").alias("city_name")
    )
    return parsed.join(f.broadcast(loc), on="location_id", how="left")


@dp.materialized_view(
    name=f"{_sch('silver')}.order_lifecycle",
    comment="One row per completed order with kitchen + delivery durations.",
    table_properties=_PROPS,
)
def order_lifecycle() -> DataFrame:
    lc = (
        spark.read.table(f"{_sch('silver')}.orders_enriched")
        .filter(f.col("event_type").isin(_LIFECYCLE))
        .groupBy("order_id", "location_id", "city_name")
        .pivot("event_type", _LIFECYCLE)
        .agg(f.min("event_timestamp"))
        .withColumnsRenamed(
            {
                "order_created": "created_at",
                "kitchen_started": "kitchen_started_at",
                "kitchen_finished": "kitchen_finished_at",
                "order_ready": "order_ready_at",
                "driver_arrived": "driver_arrived_at",
                "driver_picked_up": "pickup_at",
                "delivered": "delivered_at",
            }
        )
        .withColumns(
            {
                "kitchen_min": (
                    f.unix_timestamp("kitchen_finished_at")
                    - f.unix_timestamp("kitchen_started_at")
                )
                / 60,
                "delivery_min": (
                    f.unix_timestamp("delivered_at") - f.unix_timestamp("pickup_at")
                )
                / 60,
                "total_min": (
                    f.unix_timestamp("delivered_at") - f.unix_timestamp("created_at")
                )
                / 60,
            }
        )
    )
    return lc.filter(f.col("delivered_at").isNotNull())
