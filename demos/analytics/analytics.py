#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SQL analytics + visualization on Unity Catalog data (Spark Connect).

Ported from the containerized-lakehouse `04_Analytics` notebook and rewritten for
Spark Connect + open-lakehouse conventions. Seeds a governed sales fact table in
Unity Catalog, then runs revenue / regional / window-function / daily-trend
analytics against the three-level namespace and saves charts to PNG.

Self-contained: it seeds its own `unity.analytics_demo.sales` table (external
Delta via the UC connector), so it does not depend on other demos.

Charts need matplotlib; if it is not installed the SQL analytics still run and the
chart step is skipped with a note (`pip install matplotlib` to enable).

Run:
    poetry run python demos/analytics/analytics.py
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pyspark.sql import SparkSession

# Put demos/_lib on the path (NOT demos/, which would shadow the `mlflow` package
# with the demos/mlflow app dir) and import the helper module directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from delta_helpers import recreate_delta_table  # noqa: E402

REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
SCHEMA = "unity.analytics_demo"
TABLE = f"{SCHEMA}.sales"
# UC-registered LOCATION uses the s3:// scheme (vending rejects s3a://).
LOCATION = "s3://lakehouse/warehouse/analytics/sales"
# Chart output dir: script-relative default so it matches teardown.sh regardless of
# the caller's cwd; override both with LAKEHOUSE_ANALYTICS_OUT.
OUTPUT_DIR = Path(
    os.environ.get(
        "LAKEHOUSE_ANALYTICS_OUT", str(Path(__file__).resolve().parent / "charts")
    )
)

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
COLUMNS = [
    "transaction_id",
    "customer_id",
    "product",
    "quantity",
    "amount",
    "region",
    "transaction_date",
]


def generate_rows(n: int) -> list[tuple]:
    """Sales rows over the 30 days ending on the run date.

    Row *values* (product / region / quantity / amount) are seeded, so the
    revenue / regional / customer aggregations are reproducible run to run. The
    date window is anchored to today, so the "last 30 days" trend stays current
    rather than a fixed historical period.
    """
    random.seed(42)
    today = datetime.now()
    rows = []
    for i in range(n):
        rows.append(
            (
                f"TXN-{i + 1:06d}",
                f"customer_{random.randint(1, 200):04d}",
                random.choice(PRODUCTS),
                random.randint(1, 5),
                round(random.uniform(10, 2000), 2),
                random.choice(REGIONS),
                (today - timedelta(days=random.randint(0, 29))).strftime("%Y-%m-%d"),
            )
        )
    return rows


def seed(spark: SparkSession) -> None:
    """Register a governed sales fact table (external Delta) and fill it."""
    sales = spark.createDataFrame(generate_rows(5000), COLUMNS)
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    # recreate_delta_table makes a re-run clean (no teardown required between runs).
    recreate_delta_table(spark, TABLE, LOCATION, sales)
    n = spark.table(TABLE).count()
    print(f"[0] Seeded {TABLE}: {n:,} rows")


def make_charts(product_pd, regional_pd, daily_pd) -> None:
    """Save the three charts to PNG (skipped cleanly if matplotlib is absent)."""
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "[5] matplotlib not installed; skipping charts (pip install matplotlib to enable)"
        )
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    axes[0].barh(product_pd["product"], product_pd["total_revenue"], color="#3b82f6")
    axes[0].set_xlabel("Total Revenue ($)")
    axes[0].set_title("Revenue by Product", fontweight="bold")
    axes[0].grid(axis="x", alpha=0.3)
    axes[1].pie(
        regional_pd["revenue"],
        labels=regional_pd["region"],
        autopct="%1.1f%%",
        colors=["#3b82f6", "#10b981", "#f59e0b", "#ef4444"],
        startangle=90,
    )
    axes[1].set_title("Revenue by Region", fontweight="bold")
    fig.tight_layout()
    p1 = OUTPUT_DIR / "revenue_by_product_and_region.png"
    fig.savefig(p1, dpi=100)

    trend = daily_pd.sort_values("transaction_date")
    fig2, ax1 = plt.subplots(figsize=(14, 5))
    ax1.bar(range(len(trend)), trend["revenue"], alpha=0.3, color="#3b82f6")
    ax1.set_ylabel("Daily Revenue ($)", color="#3b82f6")
    ax2 = ax1.twinx()
    ax2.plot(
        range(len(trend)), trend["cumulative_revenue"], color="#ef4444", linewidth=2
    )
    ax2.set_ylabel("Cumulative Revenue ($)", color="#ef4444")
    ax1.set_title("Daily Revenue Trend (last 30 days)", fontweight="bold")
    ax1.set_xlabel("Day")
    fig2.tight_layout()
    p2 = OUTPUT_DIR / "daily_revenue_trend.png"
    fig2.savefig(p2, dpi=100)

    # Print paths relative to the cwd so the output matches the README (e.g.
    # demos/analytics/charts/... when run from the repo root).
    print(f"[5] Charts saved: {os.path.relpath(p1)}, {os.path.relpath(p2)}")


def main() -> None:
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    print(f"Spark {spark.version} ready (remote={REMOTE})")

    seed(spark)

    # --- 1. Revenue by product ----------------------------------------------
    product_revenue = spark.sql(f"""
        SELECT product, COUNT(*) AS orders, SUM(quantity) AS units_sold,
               ROUND(SUM(amount), 2) AS total_revenue, ROUND(AVG(amount), 2) AS avg_order_value
        FROM {TABLE} GROUP BY product ORDER BY total_revenue DESC
        """)
    print("\n[1] Revenue by product:")
    product_revenue.show(truncate=False)

    # --- 2. Regional performance (pct of total via window) ------------------
    regional = spark.sql(f"""
        SELECT region, COUNT(*) AS orders, ROUND(SUM(amount), 2) AS revenue,
               ROUND(AVG(amount), 2) AS avg_order,
               ROUND(SUM(amount) * 100.0 / SUM(SUM(amount)) OVER (), 2) AS pct_of_total
        FROM {TABLE} GROUP BY region ORDER BY revenue DESC
        """)
    print("[2] Regional performance:")
    regional.show(truncate=False)

    # --- 3. Window functions: top 3 customers per region -------------------
    top_customers = spark.sql(f"""
        WITH customer_totals AS (
            SELECT customer_id, region, COUNT(*) AS orders, ROUND(SUM(amount), 2) AS total_spent
            FROM {TABLE} GROUP BY customer_id, region
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY total_spent DESC) AS rank
            FROM customer_totals
        )
        SELECT region, customer_id, orders, total_spent, rank
        FROM ranked WHERE rank <= 3 ORDER BY region, rank
        """)
    print("[3] Top 3 customers per region:")
    top_customers.show(truncate=False)

    # --- 4. Daily sales trend (cumulative via window) -----------------------
    daily_trend = spark.sql(f"""
        SELECT transaction_date, COUNT(*) AS orders, ROUND(SUM(amount), 2) AS revenue,
               ROUND(SUM(SUM(amount)) OVER (
                   ORDER BY transaction_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ), 2) AS cumulative_revenue
        FROM {TABLE} GROUP BY transaction_date ORDER BY transaction_date
        """)
    print("[4] Daily sales trend (head):")
    daily_trend.show(5, truncate=False)

    # --- 5. Visualization (PNG) ---------------------------------------------
    make_charts(product_revenue.toPandas(), regional.toPandas(), daily_trend.toPandas())

    print("\nanalytics demo complete.")
    spark.stop()


if __name__ == "__main__":
    main()
