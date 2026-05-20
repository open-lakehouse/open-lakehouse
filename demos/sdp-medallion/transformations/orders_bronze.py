"""Bronze layer.

`table_properties.location` + `provider=delta` is required to satisfy UC OSS's
Spark connector, which asserts location != null in createTable and asserts
provider != null in its proxy layer. SDP's SQL `LOCATION` clause is explicitly
rejected ("storage location is managed by the pipeline"), so the Python
decorator is the only way to pass these through.
"""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

spark = SparkSession.active()

WAREHOUSE = "s3://lakehouse/warehouse/sdp/v2/bronze"


@dp.materialized_view(
    name="orders_bronze",
    comment="Synthetic orders landed as bronze (5 rows).",
    table_properties={
        "location": f"{WAREHOUSE}/orders_bronze",
        "provider": "delta",
    },
)
def orders_bronze() -> DataFrame:
    return spark.range(5).selectExpr(
        "id + 1 AS order_id",
        "concat('cust_', cast(id + 1 AS STRING)) AS customer",
        "(id + 1) * 10.0 AS amount",
        "date_add(DATE '2026-05-17', cast(id % 3 AS INT)) AS order_date",
    )
