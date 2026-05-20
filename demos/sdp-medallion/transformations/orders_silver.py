"""Silver layer: cleaned + typed from bronze.

Python decorator (not SQL) because we need to pass location + provider
through table_properties — SDP's SQL parser rejects LOCATION on CREATE
MATERIALIZED VIEW.
"""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

spark = SparkSession.active()

WAREHOUSE = "s3://lakehouse/warehouse/sdp/v2/bronze"


@dp.materialized_view(
    name="orders_silver",
    comment="Orders with positive amounts only.",
    table_properties={
        "location": f"{WAREHOUSE}/orders_silver",
        "provider": "delta",
    },
)
def orders_silver() -> DataFrame:
    return spark.read.table("orders_bronze").where("amount > 0")
