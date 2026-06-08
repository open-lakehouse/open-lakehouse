"""Bronze layer — raw food-delivery order events + location dimension.

Real SDP (`pyspark.pipelines`): each function returns a DataFrame; SDP infers the
DAG and materializes Delta tables in Unity Catalog. The `table_properties`
location (s3:// scheme) + provider=delta are mandatory for UC OSS — see
.claude/skills/sdp/unity-catalog.md.

Env knobs (defaults target the LOCAL stack: SeaweedFS + local UC):
  DEMO_NS               schema/location prefix for per-presenter isolation ("" local)
  MEDALLION_WAREHOUSE   s3:// base for managed Delta locations
  ORDERS_PATH           raw orders parquet (/data locally; s3a:// when hosted)
  DIMS_PATH             dimension parquet dir
  MEDALLION_MAX_ROWS    cap raw events so the demo stays inside the 2-3 min budget
"""
import os

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as f

spark = SparkSession.active()

NS = os.environ.get("DEMO_NS", "")
ORDERS_PATH = os.environ.get("ORDERS_PATH", "/data/events/orders_7d.parquet")
DIMS_PATH = os.environ.get("DIMS_PATH", "/data/dimensions")
MAX_ROWS = int(os.environ.get("MEDALLION_MAX_ROWS", "500000"))

# Catalog-managed Delta tables: the catalog assigns storage under its
# storage_root, so no explicit location — only provider + the catalogManaged
# feature flag (required by managed_demo on Scott's UC).
_PROPS = {"provider": "delta", "delta.feature.catalogManaged": "supported"}


def _sch(layer: str) -> str:
    return f"{NS}{layer}"


@dp.materialized_view(
    name=f"{_sch('bronze')}.orders",
    comment="Raw food-delivery order lifecycle events, timestamp-parsed.",
    table_properties=_PROPS,
)
def orders() -> DataFrame:
    return (
        spark.read.parquet(ORDERS_PATH)
        .limit(MAX_ROWS)
        .withColumn("event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " ")))
    )


@dp.materialized_view(
    name=f"{_sch('bronze')}.dim_locations",
    comment="Location dimension (id -> city).",
    table_properties=_PROPS,
)
def dim_locations() -> DataFrame:
    return spark.read.parquet(f"{DIMS_PATH}/locations.parquet")
