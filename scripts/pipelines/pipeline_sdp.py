"""Ghost-kitchen medallion pipeline — Spark Declarative Pipelines (OSS).

A richer reference pipeline than `demos/sdp-medallion/`: batch + streaming
ingestion, an enrich/pivot silver layer, and three gold aggregations over
synthetic ghost-kitchen order data.

OSS Spark 4.1 `pyspark.pipelines` — NOT Databricks DLT. See
`.claude/skills/sdp/` for the API and `.claude/skills/sdp/unity-catalog.md`
for why every table carries an explicit `location` + `provider`.

Run:
    # generate the parquet inputs first
    ./lakehouse testdata generate --days 90 && ./lakehouse testdata load

    docker exec spark-master-41 sh -c \
      'cd /scripts/pipelines && spark-pipelines run'

Datasets (all in catalog `unity`, schema `medallion`):
    bronze_*  — raw ingest (dimensions + orders, batch and Kafka streaming)
    silver_*  — cleaned, enriched, pivoted
    gold_*    — business aggregations
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# OSS SDP does not inject `spark` — acquire the active session explicitly.
spark = SparkSession.active()

# UC's Spark connector requires an explicit storage location + provider on
# every table (it asserts on both). Build them off one warehouse root.
_WAREHOUSE = "s3://lakehouse/warehouse/sdp/medallion"


def _delta(name: str) -> dict:
    """table_properties for a UC-managed Delta table at a per-table location."""
    return {"location": f"{_WAREHOUSE}/{name}", "provider": "delta"}


# =============================================================================
# BRONZE — raw ingestion
# =============================================================================
# Dimensions: batch parquet from the testdata generator. Pure batch sources,
# so materialized views (not streaming tables).


@dp.materialized_view(
    name="bronze_dim_categories", table_properties=_delta("bronze_dim_categories")
)
def bronze_dim_categories():
    """Food categories dimension."""
    return spark.read.parquet("/data/dimensions/categories.parquet")


@dp.materialized_view(
    name="bronze_dim_brands", table_properties=_delta("bronze_dim_brands")
)
def bronze_dim_brands():
    """Ghost-kitchen brands dimension."""
    return spark.read.parquet("/data/dimensions/brands.parquet")


@dp.materialized_view(
    name="bronze_dim_items", table_properties=_delta("bronze_dim_items")
)
def bronze_dim_items():
    """Menu items dimension."""
    return spark.read.parquet("/data/dimensions/items.parquet")


@dp.materialized_view(
    name="bronze_dim_locations", table_properties=_delta("bronze_dim_locations")
)
def bronze_dim_locations():
    """Delivery locations dimension."""
    return spark.read.parquet("/data/dimensions/locations.parquet")


@dp.materialized_view(name="bronze_orders", table_properties=_delta("bronze_orders"))
def bronze_orders():
    """Order lifecycle events from the batch parquet source."""
    return spark.read.parquet("/data/events/orders_90d.parquet").withColumn(
        "event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


# Kafka ingestion → streaming table (@dp.table over a streaming source).
@dp.table(
    name="bronze_orders_streaming", table_properties=_delta("bronze_orders_streaming")
)
def bronze_orders_streaming():
    """Order lifecycle events from the Kafka `orders` topic."""
    event_schema = StructType(
        [
            StructField("event_id", StringType()),
            StructField("event_type", StringType()),
            StructField("ts", StringType()),
            StructField("ts_seconds", IntegerType()),
            StructField("order_id", StringType()),
            StructField("location_id", IntegerType()),
            StructField("sequence", IntegerType()),
            StructField("body", StringType()),
        ]
    )

    parsed = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", "kafka:9092")
        .option("subscribe", "orders")
        .option("startingOffsets", "latest")
        .load()
        .select(
            f.from_json(f.col("value").cast("string"), event_schema).alias("event"),
            f.col("timestamp").alias("kafka_timestamp"),
        )
        .select("event.*", "kafka_timestamp")
    )

    return parsed.withColumn(
        "event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


# =============================================================================
# SILVER — cleaned & enriched
# =============================================================================


@dp.materialized_view(
    name="silver_orders_enriched", table_properties=_delta("silver_orders_enriched")
)
def silver_orders_enriched():
    """Orders with parsed JSON body, time features, and a location join.

    Dependencies (inferred from the spark.read.table calls below):
    bronze_orders, bronze_dim_locations.
    """
    orders = spark.read.table("bronze_orders")

    cleaned = orders.filter(
        f.col("event_id").isNotNull()
        & f.col("order_id").isNotNull()
        & f.col("event_timestamp").isNotNull()
    )

    body_schema = StructType(
        [
            StructField("brand_id", IntegerType()),
            StructField("item_ids", StringType()),
            StructField("total", DoubleType()),
            StructField("lat", DoubleType()),
            StructField("lng", DoubleType()),
            StructField("driver_id", StringType()),
        ]
    )

    enriched = cleaned.withColumn(
        "body_parsed", f.from_json("body", body_schema)
    ).select(
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

    enriched = enriched.withColumns(
        {
            "event_hour": f.hour("event_timestamp"),
            "event_day_of_week": f.dayofweek("event_timestamp"),
            "is_weekend": f.when(
                f.dayofweek("event_timestamp").isin(1, 7), True
            ).otherwise(False),
            "event_date": f.to_date("event_timestamp"),
        }
    )

    locations = spark.read.table("bronze_dim_locations").select(
        f.col("id").alias("location_id"),
        f.col("city").alias("city_name"),
    )

    return enriched.join(f.broadcast(locations), on="location_id", how="left")


@dp.materialized_view(
    name="silver_order_lifecycle", table_properties=_delta("silver_order_lifecycle")
)
def silver_order_lifecycle():
    """One row per completed order, with per-stage timestamps and durations."""
    orders = spark.read.table("silver_orders_enriched")

    lifecycle = (
        orders.groupBy("order_id", "location_id", "city_name")
        .pivot(
            "event_type",
            [
                "order_created",
                "kitchen_started",
                "kitchen_finished",
                "order_ready",
                "driver_arrived",
                "driver_picked_up",
                "delivered",
            ],
        )
        .agg(f.min("event_timestamp").alias("ts"))
        .select(
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
    )

    lifecycle = lifecycle.withColumns(
        {
            "kitchen_duration_min": (
                f.unix_timestamp("kitchen_finished_at")
                - f.unix_timestamp("kitchen_started_at")
            )
            / 60,
            "delivery_duration_min": (
                f.unix_timestamp("delivered_at") - f.unix_timestamp("pickup_at")
            )
            / 60,
            "total_duration_min": (
                f.unix_timestamp("delivered_at") - f.unix_timestamp("created_at")
            )
            / 60,
        }
    )

    return lifecycle.filter(f.col("delivered_at").isNotNull())


# =============================================================================
# GOLD — business aggregations
# =============================================================================


@dp.materialized_view(
    name="gold_hourly_metrics", table_properties=_delta("gold_hourly_metrics")
)
def gold_hourly_metrics():
    """Hourly order metrics by location."""
    return (
        spark.read.table("silver_orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("event_date", "event_hour", "location_id", "city_name")
        .agg(
            f.count("order_id").alias("order_count"),
            f.sum("order_total").alias("total_revenue"),
            f.avg("order_total").alias("avg_order_value"),
            f.countDistinct("brand_id").alias("unique_brands"),
        )
    )


@dp.materialized_view(
    name="gold_delivery_performance",
    table_properties=_delta("gold_delivery_performance"),
)
def gold_delivery_performance():
    """Delivery performance metrics by date and location."""
    return (
        spark.read.table("silver_order_lifecycle")
        .groupBy(
            f.to_date("created_at").alias("order_date"),
            "location_id",
            "city_name",
        )
        .agg(
            f.count("order_id").alias("completed_orders"),
            f.avg("kitchen_duration_min").alias("avg_kitchen_time_min"),
            f.avg("delivery_duration_min").alias("avg_delivery_time_min"),
            f.avg("total_duration_min").alias("avg_total_time_min"),
            f.percentile_approx("total_duration_min", 0.5).alias(
                "median_total_time_min"
            ),
            f.percentile_approx("total_duration_min", 0.95).alias("p95_total_time_min"),
        )
    )


@dp.materialized_view(
    name="gold_brand_summary", table_properties=_delta("gold_brand_summary")
)
def gold_brand_summary():
    """Brand-level summary metrics."""
    brand_metrics = (
        spark.read.table("silver_orders_enriched")
        .filter(f.col("event_type") == "order_created")
        .groupBy("brand_id")
        .agg(
            f.count("order_id").alias("total_orders"),
            f.sum("order_total").alias("total_revenue"),
            f.avg("order_total").alias("avg_order_value"),
            f.countDistinct("location_id").alias("locations_served"),
            f.min("event_date").alias("first_order_date"),
            f.max("event_date").alias("last_order_date"),
        )
    )

    brands = spark.read.table("bronze_dim_brands").select(
        f.col("id").alias("brand_id"), "name"
    )

    return brand_metrics.join(brands, on="brand_id", how="left").select(
        "brand_id",
        f.col("name").alias("brand_name"),
        "total_orders",
        "total_revenue",
        "avg_order_value",
        "locations_served",
        "first_order_date",
        "last_order_date",
    )
