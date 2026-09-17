#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Delta Lake deep dive on the open-lakehouse stack (Spark Connect).

Ported from the containerized-lakehouse `02_Delta_Lake_Deep_Dive` notebook and
rewritten for Spark Connect + the open-lakehouse conventions (SeaweedFS S3, the
`lakehouse` bucket, catalogs pre-wired in spark-defaults). Delta operations use
SQL so the demo runs entirely through `sc://localhost:15002` with no
DeltaTable/Delta-Connect client dependency.

Covers: partitioned writes, ACID DML (UPDATE / DELETE / MERGE), time travel,
schema evolution, and OPTIMIZE — against a path-based Delta table on S3.

Run:
    poetry run python demos/delta-deep-dive/deep_dive.py
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as f

# Put demos/_lib on the path (NOT demos/, which would shadow the `mlflow` package
# with the demos/mlflow app dir) and import the helper module directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from delta_helpers import clear_prefix  # noqa: E402

# Path-based Delta table under this demo's own S3 prefix (matches teardown.sh).
TABLE_PATH = "s3a://lakehouse/warehouse/delta-deep-dive/transactions"
REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
# Fixed base date so the seeded data (and stdout) are fully reproducible.
BASE_DATE = datetime(2026, 1, 1)

PRODUCTS = [
    "Laptop",
    "Phone",
    "Tablet",
    "Headphones",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Webcam",
]
REGIONS = ["North America", "Europe", "Asia", "South America"]
STATUSES = ["completed", "pending", "cancelled", "refunded"]
COLUMNS = [
    "transaction_id",
    "customer_id",
    "product",
    "quantity",
    "amount",
    "region",
    "status",
    "transaction_date",
]


def generate_rows(n: int) -> list[tuple]:
    """Deterministic e-commerce transactions (seeded + fixed base date)."""
    random.seed(42)
    rows = []
    for i in range(n):
        rows.append(
            (
                f"TXN-{i + 1:06d}",
                f"customer_{random.randint(1, 1000):04d}",
                random.choice(PRODUCTS),
                random.randint(1, 5),
                round(random.uniform(10, 2000), 2),
                random.choice(REGIONS),
                random.choice(STATUSES),
                (BASE_DATE - timedelta(days=random.randint(0, 365))).strftime(
                    "%Y-%m-%d"
                ),
            )
        )
    return rows


def main() -> None:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    # Demo-scale data: the default 200 shuffle partitions bloat memory and file
    # counts for a tiny table (and can OOM the Connect container on a modest local
    # host). 8 is plenty here.
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    print(f"Spark {spark.version} ready (remote={REMOTE})")

    # Start clean so the demo is repeatable: this is a path-based table (no UC entry
    # to DROP), and a prior run leaves an evolved schema (loyalty_tier) in the Delta
    # log that would break this run's MERGE — so clear the S3 prefix first.
    clear_prefix(TABLE_PATH)

    # --- 1. Generate + write a partitioned Delta table ----------------------
    df = spark.createDataFrame(generate_rows(5000), COLUMNS)
    df.write.format("delta").mode("overwrite").option(
        "overwriteSchema", "true"
    ).partitionBy("region").save(TABLE_PATH)
    print(f"\n[1] Created {df.count():,} transactions, partitioned by region")
    spark.read.format("delta").load(TABLE_PATH).groupBy("region").count().orderBy(
        f.desc("count")
    ).show()

    # --- 2. ACID transactions (UPDATE / DELETE / MERGE via SQL) -------------
    spark.sql(
        f"UPDATE delta.`{TABLE_PATH}` SET amount = amount * 0.9 WHERE amount > 1000"
    )
    print("[2] UPDATE: applied 10% discount to orders > $1,000")

    before = spark.read.format("delta").load(TABLE_PATH).count()
    spark.sql(f"DELETE FROM delta.`{TABLE_PATH}` WHERE status = 'cancelled'")
    after = spark.read.format("delta").load(TABLE_PATH).count()
    print(
        f"[2] DELETE: removed {before - after:,} cancelled orders ({after:,} remaining)"
    )

    spark.sql(f"""
        MERGE INTO delta.`{TABLE_PATH}` AS target
        USING (
            SELECT * FROM VALUES
                ('TXN-000001','customer_0001','Laptop',1,899.99,'Europe','completed','2025-03-01'),
                ('TXN-999999','customer_0500','Monitor',2,449.99,'Asia','completed','2025-03-01')
            AS s({",".join(COLUMNS)})
        ) AS source
        ON target.transaction_id = source.transaction_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """)
    final = spark.read.format("delta").load(TABLE_PATH).count()
    print(f"[2] MERGE: upserted 2 orders (1 update + 1 insert); final count {final:,}")

    # --- 3. Time travel -----------------------------------------------------
    print("\n[3] Delta transaction history:")
    spark.sql(f"DESCRIBE HISTORY delta.`{TABLE_PATH}`").select(
        "version", "operation"
    ).show(truncate=False)
    v0 = spark.read.format("delta").option("versionAsOf", 0).load(TABLE_PATH).count()
    latest = spark.read.format("delta").load(TABLE_PATH).count()
    print(
        f"[3] version 0 (original): {v0:,} rows | latest: {latest:,} rows | delta: {v0 - latest:,}"
    )

    # --- 4. Schema evolution (append a new column with mergeSchema) ---------
    enriched = spark.createDataFrame(
        [
            (
                "TXN-900001",
                "customer_0100",
                "Laptop",
                1,
                1200.00,
                "Europe",
                "completed",
                "2025-03-02",
                "premium",
            )
        ],
        COLUMNS + ["loyalty_tier"],
    )
    enriched.write.format("delta").mode("append").option("mergeSchema", "true").save(
        TABLE_PATH
    )
    cols = spark.read.format("delta").load(TABLE_PATH).columns
    print(f"\n[4] Schema evolved; columns now: {cols}")

    # --- 5. Table optimization ----------------------------------------------
    print("\n[5] Running OPTIMIZE (compact small files)...")
    spark.sql(f"OPTIMIZE delta.`{TABLE_PATH}`")
    detail = (
        spark.sql(f"DESCRIBE DETAIL delta.`{TABLE_PATH}`")
        .select("format", "numFiles", "sizeInBytes")
        .first()
    )
    print(
        f"[5] format={detail['format']} numFiles={detail['numFiles']} sizeInBytes={detail['sizeInBytes']:,}"
    )

    print("\ndelta-deep-dive complete.")
    spark.stop()


if __name__ == "__main__":
    main()
