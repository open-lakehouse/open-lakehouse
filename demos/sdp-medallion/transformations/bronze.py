"""Bronze layer - ingestion only.

The only Python in the pipeline: SDP can't read external parquet from a SQL
`FROM` clause, so the two raw inputs are read here. Everything downstream
(silver, gold) is pure declarative SQL - see the .sql files in this directory.

Catalog-managed Delta in Unity Catalog: provider + the catalogManaged feature
flag, no explicit location (the catalog assigns it under its storage root).
"""
import os

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

ORDERS_PATH = os.environ.get("ORDERS_PATH", "/data/events/orders_7d.parquet")
DIMS_PATH = os.environ.get("DIMS_PATH", "/data/dimensions")
MAX_ROWS = int(os.environ.get("MEDALLION_MAX_ROWS", "200000"))

_PROPS = {"provider": "delta", "delta.feature.catalogManaged": "supported"}


@dp.materialized_view(
    name="orders_bronze",
    comment="Raw food-delivery order events ingested from object storage.",
    table_properties=_PROPS,
)
def orders_bronze() -> DataFrame:
    return (
        spark.read.parquet(ORDERS_PATH)
        .limit(MAX_ROWS)
        .withColumn("event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " ")))
    )


@dp.materialized_view(
    name="dim_locations",
    comment="Location dimension (id -> city).",
    table_properties=_PROPS,
)
def dim_locations() -> DataFrame:
    return spark.read.parquet(f"{DIMS_PATH}/locations.parquet")
