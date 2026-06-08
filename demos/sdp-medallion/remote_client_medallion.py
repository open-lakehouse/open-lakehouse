#!/usr/bin/env python3
"""Declarative (SDP-style) medallion, executed on the REMOTE Spark cluster.

Authoring model mirrors Spark Declarative Pipelines: each table is a function
that RETURNS a DataFrame and declares upstreams via ``p.table("layer.name")``;
dependencies are inferred and the graph is topologically executed. But unlike
the real ``spark-pipelines`` runtime (which spawns its own local Spark), this
submits every stage to Scott's hosted Spark Connect server, so all compute runs
on the remote cluster. Outputs are Delta tables registered in Unity Catalog.

Data source: real food-delivery order events staged in S3
  s3a://uc-quickstart-207734640204-usw2/medallion-demo/raw/{orders,dimensions}/

Token: $UC_TOKEN or ~/.uc_token (a valid UC bearer JWT).

Run:
  python3 demos/sdp-medallion/remote_client_medallion.py          # build all
  python3 demos/sdp-medallion/remote_client_medallion.py --show   # read-only peek
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path
from typing import Callable

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

REMOTE = "sc://connect.openlakehousedemos.dev:443/;use_ssl=true"
UC_URI = "https://uc.openlakehousedemos.dev"
CATALOG = "unity"
RAW = "s3a://uc-quickstart-207734640204-usw2/medallion-demo/raw"


# --------------------------------------------------------------------------- #
# Token + session
# --------------------------------------------------------------------------- #
def load_token() -> str:
    tok = os.environ.get("UC_TOKEN", "").strip()
    if not tok and (Path.home() / ".uc_token").exists():
        tok = (Path.home() / ".uc_token").read_text().strip()
    if not tok:
        sys.exit("No UC token. Set $UC_TOKEN or write it to ~/.uc_token")
    if tok.count(".") != 2:
        sys.exit(f"Token has {tok.count('.') + 1} segments, need 3 - it's truncated.")
    return tok


def session(token: str) -> SparkSession:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    spark.conf.set(
        f"spark.sql.catalog.{CATALOG}", "io.unitycatalog.spark.UCSingleCatalog"
    )
    spark.conf.set(f"spark.sql.catalog.{CATALOG}.uri", UC_URI)
    spark.conf.set(f"spark.sql.catalog.{CATALOG}.token", token)
    return spark


# --------------------------------------------------------------------------- #
# Mini declarative framework (SDP-style authoring, remote execution)
# --------------------------------------------------------------------------- #
class Pipeline:
    def __init__(self, spark: SparkSession, catalog: str = CATALOG):
        self.spark = spark
        self.catalog = catalog
        self.defs: dict[str, dict] = {}

    def mv(self, name: str, layer: str):
        """Register a materialized view. key = '<layer>.<name>'."""

        def deco(fn: Callable[[], DataFrame]):
            deps = set(
                re.findall(r'p\.table\(["\']([^"\']+)["\']\)', inspect.getsource(fn))
            )
            self.defs[f"{layer}.{name}"] = {
                "fn": fn,
                "layer": layer,
                "name": name,
                "deps": deps,
            }
            return fn

        return deco

    def table(self, key: str) -> DataFrame:
        """Read an upstream materialized table (also records the dependency)."""
        return self.spark.table(f"{self.catalog}.{key}")

    def _topo(self) -> list[str]:
        order, seen = [], set()

        def visit(k: str):
            if k in seen:
                return
            seen.add(k)
            for d in self.defs.get(k, {}).get("deps", ()):
                visit(d)
            if k in self.defs:
                order.append(k)

        for k in self.defs:
            visit(k)
        return order

    def run(self) -> None:
        for layer in sorted({d["layer"] for d in self.defs.values()}):
            self.spark.sql(f"CREATE SCHEMA IF NOT EXISTS {self.catalog}.{layer}")
            print(f"  schema ready: {self.catalog}.{layer}")
        for key in self._topo():
            df = self.defs[key]["fn"]()
            target = f"{self.catalog}.{key}"
            df.writeTo(target).using("delta").createOrReplace()
            print(f"  {target}: {self.spark.table(target).count():,} rows")


# --------------------------------------------------------------------------- #
# Schema of the JSON `body` (matches the REAL orders_7d data)
# --------------------------------------------------------------------------- #
ITEM = StructType(
    [
        StructField("item_id", IntegerType()),
        StructField("name", StringType()),
        StructField("price", DoubleType()),
        StructField("quantity", IntegerType()),
    ]
)
BODY = StructType(
    [
        StructField("customer_lat", DoubleType()),
        StructField("customer_lon", DoubleType()),
        StructField("brand_id", IntegerType()),
        StructField("brand_name", StringType()),
        StructField("items", ArrayType(ITEM)),
        StructField("total", DoubleType()),
    ]
)

LIFECYCLE_EVENTS = [
    "order_created",
    "kitchen_started",
    "kitchen_finished",
    "order_ready",
    "driver_arrived",
    "driver_picked_up",
    "delivered",
]  # excludes high-volume "driver_ping" GPS noise


# --------------------------------------------------------------------------- #
# Pipeline definitions  (p is bound in main())
# --------------------------------------------------------------------------- #
def define(p: Pipeline) -> None:
    # ---- BRONZE: dimensions + raw orders ----
    @p.mv("dim_brands", "bronze")
    def _():
        return p.spark.read.parquet(f"{RAW}/dimensions/brands.parquet")

    @p.mv("dim_items", "bronze")
    def _():
        return p.spark.read.parquet(f"{RAW}/dimensions/items.parquet")

    @p.mv("dim_categories", "bronze")
    def _():
        return p.spark.read.parquet(f"{RAW}/dimensions/categories.parquet")

    @p.mv("dim_locations", "bronze")
    def _():
        return p.spark.read.parquet(f"{RAW}/dimensions/locations.parquet")

    @p.mv("orders", "bronze")
    def _():
        return p.spark.read.parquet(f"{RAW}/orders/orders_7d.parquet").withColumn(
            "event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " "))
        )

    # ---- SILVER: enriched events + per-order lifecycle ----
    @p.mv("orders_enriched", "silver")
    def _():
        orders = p.table("bronze.orders").filter(
            f.col("event_id").isNotNull()
            & f.col("order_id").isNotNull()
            & f.col("event_timestamp").isNotNull()
        )
        b = (
            orders.withColumn("b", f.from_json("body", BODY))
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
        loc = p.table("bronze.dim_locations").select(
            f.col("id").alias("location_id"), f.col("city").alias("city_name")
        )
        return b.join(f.broadcast(loc), on="location_id", how="left")

    @p.mv("order_lifecycle", "silver")
    def _():
        lc = (
            p.table("silver.orders_enriched")
            .filter(f.col("event_type").isin(LIFECYCLE_EVENTS))
            .groupBy("order_id", "location_id", "city_name")
            .pivot("event_type", LIFECYCLE_EVENTS)
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
                        f.unix_timestamp("delivered_at")
                        - f.unix_timestamp("created_at")
                    )
                    / 60,
                }
            )
        )
        return lc.filter(f.col("delivered_at").isNotNull())

    # ---- GOLD: business aggregations ----
    @p.mv("hourly_metrics", "gold")
    def _():
        return (
            p.table("silver.orders_enriched")
            .filter(f.col("event_type") == "order_created")
            .groupBy("event_date", "event_hour", "location_id", "city_name")
            .agg(
                f.count("order_id").alias("order_count"),
                f.round(f.sum("order_total"), 2).alias("total_revenue"),
                f.round(f.avg("order_total"), 2).alias("avg_order_value"),
                f.countDistinct("brand_id").alias("unique_brands"),
            )
        )

    @p.mv("delivery_performance", "gold")
    def _():
        return (
            p.table("silver.order_lifecycle")
            .groupBy(
                f.to_date("created_at").alias("order_date"), "location_id", "city_name"
            )
            .agg(
                f.count("order_id").alias("completed_orders"),
                f.round(f.avg("kitchen_min"), 1).alias("avg_kitchen_min"),
                f.round(f.avg("delivery_min"), 1).alias("avg_delivery_min"),
                f.round(f.avg("total_min"), 1).alias("avg_total_min"),
                f.round(f.percentile_approx("total_min", 0.5), 1).alias(
                    "p50_total_min"
                ),
                f.round(f.percentile_approx("total_min", 0.95), 1).alias(
                    "p95_total_min"
                ),
            )
        )

    @p.mv("brand_summary", "gold")
    def _():
        return (
            p.table("silver.orders_enriched")
            .filter(f.col("event_type") == "order_created")
            .groupBy("brand_id", "brand_name")
            .agg(
                f.count("order_id").alias("total_orders"),
                f.round(f.sum("order_total"), 2).alias("total_revenue"),
                f.round(f.avg("order_total"), 2).alias("avg_order_value"),
                f.countDistinct("location_id").alias("locations_served"),
                f.min("event_date").alias("first_order_date"),
                f.max("event_date").alias("last_order_date"),
            )
            .orderBy(f.desc("total_revenue"))
        )


# --------------------------------------------------------------------------- #
def main() -> None:
    show_only = "--show" in sys.argv
    spark = session(load_token())
    print(f"connected: {REMOTE}")
    print("catalogs:", [r[0] for r in spark.sql("SHOW CATALOGS").collect()])
    p = Pipeline(spark)
    define(p)

    if show_only:
        for layer in ("bronze", "silver", "gold"):
            try:
                tbls = spark.sql(f"SHOW TABLES IN {CATALOG}.{layer}").collect()
                for t in tbls:
                    print(f"  {CATALOG}.{layer}.{t[1]}")
            except Exception as e:
                print(f"  ({layer}: {repr(e)[:80]})")
        spark.stop()
        return

    print(f"\nbuilding medallion ({len(p.defs)} tables, topo order)...")
    p.run()
    print("\ngold.brand_summary (top brands by revenue):")
    spark.table(f"{CATALOG}.gold.brand_summary").show(10, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
