"""AFTER — the same medallion pipeline as Spark Declarative Pipelines.

Three `@dp` functions. No write statements, no checkpoint paths, no manual
ordering. SDP infers the DAG from the `spark.read.table(...)` calls:
dec_orders_bronze → dec_orders_silver → dec_orders_gold, run in that order.

Source: the generated order-event dataset (`data/events/orders_7d.parquet`,
~8M events). Materialized into Unity Catalog under `unity.i2d`. Compare
line-for-line with ../imperative_pipeline.py.
"""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

# UC OSS's Spark connector asserts location != null and provider != null on
# createTable; SDP's SQL LOCATION clause is rejected, so each table passes them
# through `table_properties`. The explicit location makes these UC *external*
# tables — SDP cannot create UC catalog-managed tables (Delta rejects it).
# (s3:// — the scheme UC stores; mapped to S3A.)
_WAREHOUSE = "s3://lakehouse/warehouse/sdp/v2/i2d"

# Declared schemas — SDP analyses each function when it builds the graph, so
# the parquet reader must not do I/O-based schema inference there. `_EVENTS`
# is the event-file schema; `_BODY` is the JSON `body` column.
_EVENTS = (
    "event_id STRING, event_type STRING, ts STRING, ts_seconds BIGINT, "
    "location_id INT, order_id STRING, sequence INT, body STRING"
)
_BODY = (
    "customer_lat DOUBLE, customer_lon DOUBLE, brand_id BIGINT, "
    "brand_name STRING, "
    "items ARRAY<STRUCT<item_id BIGINT, name STRING, price DOUBLE, quantity BIGINT>>, "
    "total DOUBLE"
)


def _uc(name: str) -> dict:
    """table_properties for a UC external Delta table."""
    return {"location": f"{_WAREHOUSE}/{name}", "provider": "delta"}


@dp.materialized_view(
    name="dec_orders_bronze",
    comment="Raw order events, body parsed.",
    table_properties=_uc("dec_orders_bronze"),
)
def dec_orders_bronze() -> DataFrame:
    return (
        spark.read.schema(_EVENTS).parquet("file:///data/events/orders_7d.parquet")
        .where("event_type = 'order_created'")
        .withColumn("o", f.from_json("body", _BODY))
        .select(
            "order_id",
            f.to_timestamp("ts").alias("order_ts"),
            "location_id",
            f.col("o.brand_name").alias("brand"),
            f.col("o.total").alias("order_total"),
            f.size("o.items").alias("item_count"),
        )
    )


@dp.materialized_view(
    name="dec_orders_silver",
    comment="Cleaned, valid orders.",
    table_properties=_uc("dec_orders_silver"),
)
def dec_orders_silver() -> DataFrame:
    # Dependency on dec_orders_bronze is inferred from this read — no ordering code.
    return (
        spark.read.table("dec_orders_bronze")
        .where("order_total > 0")
        .withColumn("order_date", f.to_date("order_ts"))
    )


@dp.materialized_view(
    name="dec_orders_gold",
    comment="Daily revenue rollup.",
    table_properties=_uc("dec_orders_gold"),
)
def dec_orders_gold() -> DataFrame:
    return (
        spark.read.table("dec_orders_silver")
        .groupBy("order_date")
        .agg(
            f.count("*").alias("order_count"),
            f.round(f.sum("order_total"), 2).alias("revenue"),
        )
    )
