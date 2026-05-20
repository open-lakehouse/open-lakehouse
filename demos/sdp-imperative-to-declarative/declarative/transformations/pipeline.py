"""AFTER — the same medallion pipeline as Spark Declarative Pipelines.

Three `@dp` functions. No write statements, no checkpoint paths, no manual
ordering. SDP infers the DAG from the `spark.read.table(...)` calls:
dec_orders_bronze → dec_orders_silver → dec_orders_gold, run in that order.

Compare line-for-line with ../imperative_pipeline.py.
"""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()


@dp.materialized_view(name="dec_orders_bronze", comment="Synthetic orders.")
def dec_orders_bronze() -> DataFrame:
    return spark.range(200).selectExpr(
        "id AS order_id",
        "concat('cust_', cast(id % 25 AS STRING)) AS customer",
        "(id % 50) * 2.0 AS amount",
        "date_add(DATE '2026-05-01', cast(id % 7 AS INT)) AS order_date",
    )


@dp.materialized_view(name="dec_orders_silver", comment="Positive-amount orders.")
def dec_orders_silver() -> DataFrame:
    # Dependency on dec_orders_bronze is inferred from this read — no ordering code.
    return (
        spark.read.table("dec_orders_bronze")
        .where("amount > 0")
        .withColumn("_clean_ts", f.current_timestamp())
    )


@dp.materialized_view(name="dec_orders_gold", comment="Daily revenue rollup.")
def dec_orders_gold() -> DataFrame:
    return (
        spark.read.table("dec_orders_silver")
        .groupBy("order_date")
        .agg(
            f.count("*").alias("order_count"),
            f.sum("amount").alias("revenue"),
        )
    )
