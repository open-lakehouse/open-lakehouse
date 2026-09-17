"""Generate a tiny, self-contained input dataset for the sdp-medallion demo.

The medallion transforms read two parquet inputs (bronze.py):
  - ORDERS_PATH  (default /data/events/orders_7d.parquet): raw order events with a
    JSON `body` column.
  - DIMS_PATH/locations.parquet (default /data/dimensions): a location dimension.

Historically these came from an external demo bucket, which made the demo
non-runnable on a clean local stack. This script writes a small deterministic
dataset so `spark-pipelines run` works out of the box. Run it once before the
pipeline:

    docker exec spark-master-41 /opt/spark/bin/spark-submit \
      /scripts/../demos/sdp-medallion/seed.py

(or via the container path the README documents). Writes ~40 order events + 4
locations — enough to exercise bronze -> silver -> gold with non-trivial rollups.
"""

import json
import os

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    IntegerType,
    StringType,
    StructField,
    StructType,
)

ORDERS_PATH = os.environ.get("ORDERS_PATH", "file:///data/events/orders_7d.parquet")
DIMS_DIR = os.environ.get("DIMS_PATH", "file:///data/dimensions")

spark = (
    SparkSession.builder.master("local[2]").appName("sdp-medallion-seed").getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")

# --- Location dimension --------------------------------------------------------
locations = [(1, "Amsterdam"), (2, "Rotterdam"), (3, "Utrecht"), (4, "Den Haag")]
dim_schema = StructType(
    [StructField("id", IntegerType(), False), StructField("city", StringType(), True)]
)
spark.createDataFrame(locations, dim_schema).write.mode("overwrite").parquet(
    f"{DIMS_DIR}/locations.parquet"
)

# --- Order events --------------------------------------------------------------
# Deterministic: 4 brands x 4 locations, a couple of events each, across two days
# and several hours so the gold hourly/brand rollups have something to aggregate.
brands = [
    (10, "Sushi Time"),
    (20, "Pizza Corner"),
    (30, "Green Bowl"),
    (40, "Taco Loco"),
]
rows = []
eid = 0
for day in ("2026-08-01", "2026-08-02"):
    for hour in (11, 12, 18):
        for bid, bname in brands:
            eid += 1
            loc = (eid % 4) + 1
            total = round(8.0 + (eid % 7) * 2.5, 2)
            body = json.dumps(
                {
                    "brand_id": bid,
                    "brand_name": bname,
                    "total": total,
                    "items": [{"quantity": (eid % 3) + 1}],
                }
            )
            rows.append(
                (
                    f"evt{eid:04d}",
                    "order_created",
                    f"{day}T{hour:02d}:{(eid % 60):02d}:00",
                    f"ord{eid:04d}",
                    loc,
                    body,
                )
            )

order_schema = StructType(
    [
        StructField("event_id", StringType(), False),
        StructField("event_type", StringType(), False),
        StructField("ts", StringType(), False),
        StructField("order_id", StringType(), False),
        StructField("location_id", IntegerType(), False),
        StructField("body", StringType(), False),
    ]
)
spark.createDataFrame(rows, order_schema).write.mode("overwrite").parquet(ORDERS_PATH)

print(
    f"seed complete: {len(rows)} order events -> {ORDERS_PATH}; "
    f"{len(locations)} locations -> {DIMS_DIR}/locations.parquet"
)
spark.stop()
