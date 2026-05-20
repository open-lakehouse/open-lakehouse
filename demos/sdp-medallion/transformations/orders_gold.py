"""Gold layer: per-day revenue aggregation."""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

WAREHOUSE = "s3://lakehouse/warehouse/sdp/v2/bronze"


@dp.materialized_view(
    name="orders_gold",
    comment="Daily revenue and order count.",
    table_properties={
        "location": f"{WAREHOUSE}/orders_gold",
        "provider": "delta",
    },
)
def orders_gold() -> DataFrame:
    return (
        spark.read.table("orders_silver")
        .groupBy("order_date")
        .agg(
            f.count("*").alias("order_count"),
            f.sum("amount").alias("revenue"),
        )
    )
