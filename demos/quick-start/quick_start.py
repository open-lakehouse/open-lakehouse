#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Quick start: your first governed lakehouse table (Spark Connect).

Ported from the containerized-lakehouse `01_Quick_Start` notebook and rewritten
for Spark Connect + open-lakehouse conventions. The five-minute onboarding path:
connect, create a governed Delta table in Unity Catalog, query it through the
three-level namespace, and see one Delta feature in action.

For deeper coverage see `delta-deep-dive/` (Delta mechanics) and `unity-catalog/`
(governance).

Run:
    poetry run python demos/quick-start/quick_start.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

# Put demos/_lib on the path (NOT demos/, which would shadow the `mlflow` package
# with the demos/mlflow app dir) and import the helper module directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from delta_helpers import recreate_delta_table  # noqa: E402

REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
SCHEMA = "unity.quickstart"
TABLE = f"{SCHEMA}.products"
LOCATION = "s3://lakehouse/warehouse/quick-start/products"


def main() -> None:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    print(f"[1] Spark {spark.version} ready (remote={REMOTE})")

    # --- 2. Create your first governed Delta table --------------------------
    # (This also proves object storage: the Delta write lands in SeaweedFS. We
    # use Delta rather than a raw parquet write because Delta commits via its
    # transaction log — plain parquet writes use S3A's rename committer, which
    # SeaweedFS does not support.) recreate_delta_table makes re-runs clean with
    # no teardown in between.
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    products = spark.createDataFrame(
        [
            ("P001", "Laptop", "Electronics", 999.99, 50),
            ("P002", "Mouse", "Accessories", 29.99, 200),
            ("P003", "Keyboard", "Accessories", 79.99, 150),
            ("P004", "Monitor", "Electronics", 449.99, 75),
            ("P005", "USB-C Cable", "Accessories", 12.99, 500),
        ],
        ["product_id", "name", "category", "price", "stock"],
    )
    recreate_delta_table(spark, TABLE, LOCATION, products)
    print(f"[2] Created governed Delta table {TABLE}")

    # --- 3. Query via the three-level namespace -----------------------------
    print("[3] Products (price DESC):")
    spark.sql(f"SELECT * FROM {TABLE} ORDER BY price DESC").show(truncate=False)
    spark.sql(f"SHOW TABLES IN {SCHEMA}").show()

    # --- 4. One Delta feature: an ACID update + history ---------------------
    spark.sql(
        f"UPDATE {TABLE} SET price = ROUND(price * 1.2, 2) WHERE category = 'Electronics'"
    )
    print("[4] Applied +20% to Electronics; transaction history:")
    spark.sql(f"DESCRIBE HISTORY {TABLE}").select("version", "operation").show(
        truncate=False
    )

    print("\nquick-start complete.")
    spark.stop()


if __name__ == "__main__":
    main()
