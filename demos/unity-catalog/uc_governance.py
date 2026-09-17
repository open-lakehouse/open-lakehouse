#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unity Catalog OSS governance on the open-lakehouse stack (Spark Connect).

Ported from the containerized-lakehouse `03_Unity_Catalog` notebook and rewritten
for Spark Connect + open-lakehouse conventions. Shows the three-level namespace,
schema management, external Delta table registration through the UC Spark
connector, metadata discovery (SQL + the UC REST API), and a cross-schema join.

Tables are EXTERNAL Delta registered in the `unity` catalog with an explicit
`LOCATION` under this demo's own S3 prefix — the connector's proven write path
(a location-less create wants catalog-managed; CTAS wants path-credential vending).
Each table is written with Delta `overwrite` then registered (see recreate_delta_table),
which keeps re-runs deterministic without a teardown in between.

Run:
    poetry run python demos/unity-catalog/uc_governance.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from pyspark.sql import SparkSession

# Put demos/_lib on the path (NOT demos/, which would shadow the `mlflow` package
# with the demos/mlflow app dir) and import the helper module directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from delta_helpers import recreate_delta_table  # noqa: E402

REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
UC_API = os.environ.get("UC_API", "http://localhost:8081/api/2.1/unity-catalog")

# Demo schemas in the `unity` catalog + external-table locations under one prefix.
CORE = "unity.uc_demo_core"
ANALYTICS = "unity.uc_demo_analytics"
# UC-registered LOCATIONs use the s3:// scheme (UC credential vending rejects s3a://);
# Spark still reads/writes the bytes through the s3a filesystem under the hood.
PREFIX = "s3://lakehouse/warehouse/unity-catalog"


def uc_get(path: str) -> dict:
    """GET the UC REST API (same API the Spark connector and UI use)."""
    with urllib.request.urlopen(f"{UC_API}/{path}") as resp:
        return json.loads(resp.read())


def main() -> None:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    print(f"Spark {spark.version} ready (remote={REMOTE})")

    # --- 1. Three-level namespace -------------------------------------------
    # SHOW CATALOGS over Connect lists only the session-default (`spark_catalog`);
    # the UC v2 catalogs register lazily on first reference. The REST API is the
    # authoritative catalog list.
    cats = [c["name"] for c in uc_get("catalogs").get("catalogs", [])]
    print(f"\n[1] Catalogs (UC REST): {cats}  (+ spark_catalog session default)")

    # --- 2. Schema management (idempotent) ----------------------------------
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CORE}")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {ANALYTICS}")
    print("[2] Schemas in unity:")
    spark.sql("SHOW SCHEMAS IN unity").show()

    # --- 3. Table registration (external Delta via the UC connector) --------
    # recreate_delta_table makes re-runs clean (no teardown required between runs).
    dim_regions = spark.createDataFrame(
        [
            ("NA", "North America", "USD", "UTC-5"),
            ("EU", "Europe", "EUR", "UTC+1"),
            ("AP", "Asia Pacific", "JPY", "UTC+9"),
            ("SA", "South America", "BRL", "UTC-3"),
        ],
        ["region_code", "region_name", "currency", "timezone"],
    )
    recreate_delta_table(
        spark, f"{CORE}.dim_regions", f"{PREFIX}/dim_regions", dim_regions
    )
    orders = spark.createDataFrame(
        [
            ("O-1", "NA", 120.0),
            ("O-2", "NA", 80.0),
            ("O-3", "EU", 200.0),
            ("O-4", "EU", 60.0),
            ("O-5", "AP", 150.0),
            ("O-6", "SA", 90.0),
        ],
        ["order_id", "region_code", "amount"],
    )
    recreate_delta_table(spark, f"{CORE}.orders", f"{PREFIX}/orders", orders)
    print(f"[3] Registered {CORE}.dim_regions and {CORE}.orders (external Delta)")
    spark.sql(f"SHOW TABLES IN {CORE}").show()

    # --- 4. Metadata and discovery ------------------------------------------
    print(f"[4] DESCRIBE EXTENDED {CORE}.dim_regions:")
    spark.sql(f"DESCRIBE EXTENDED {CORE}.dim_regions").show(truncate=False)

    # --- 5. UC REST API (programmatic discovery) ----------------------------
    # type / format / location are populated; UC 0.5.0's /tables omits column
    # metadata for connector-registered external tables (columns live in the Delta
    # log — see DESCRIBE above).
    table = uc_get("tables/unity.uc_demo_core.dim_regions")
    print(
        f"\n[5] UC REST tables/dim_regions: type={table['table_type']} "
        f"format={table['data_source_format']} location={table['storage_location']}"
    )

    # --- 6. Cross-schema query (register a derived table in another schema) --
    revenue = spark.sql(f"""
        SELECT r.region_name, r.currency, COUNT(*) AS order_count, ROUND(SUM(o.amount),2) AS revenue
        FROM {CORE}.orders o
        JOIN {CORE}.dim_regions r ON o.region_code = r.region_code
        GROUP BY r.region_name, r.currency
        """)
    recreate_delta_table(
        spark, f"{ANALYTICS}.revenue_by_region", f"{PREFIX}/revenue_by_region", revenue
    )
    print(f"\n[6] Cross-schema join -> {ANALYTICS}.revenue_by_region:")
    spark.sql(
        f"SELECT * FROM {ANALYTICS}.revenue_by_region ORDER BY revenue DESC"
    ).show(truncate=False)

    print("\nunity-catalog governance demo complete.")
    spark.stop()


if __name__ == "__main__":
    main()
