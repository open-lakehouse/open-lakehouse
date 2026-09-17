# Analytics and visualization

> SparkSQL analytics (revenue, regional share, window rankings, cumulative trend) on a governed Unity Catalog table, with charts saved to PNG.

## Purpose

Runs realistic analytics over a governed sales table in Unity Catalog: revenue by product,
regional performance with percent-of-total, top-N customers per region via window functions, and a
cumulative daily-revenue trend. It then renders two charts to PNG. Self-contained — it seeds its own
`unity.analytics_demo.sales` table, so no other demo has to run first.

## Prereqs

- Spark 4.1 + Connect + storage + Unity Catalog: `./lakehouse start all && ./lakehouse start unity-catalog`
- Python client deps: `poetry install`. Charts additionally need matplotlib
  (`poetry run pip install matplotlib`); without it the SQL analytics still run and the chart
  step is skipped with a note.

Transport: `SparkSession.builder.remote("sc://localhost:15002")` (or `LAKEHOUSE_SPARK_REMOTE`).
Charts are written to `demos/analytics/charts/` (override with `LAKEHOUSE_ANALYTICS_OUT`); that
directory is gitignored.

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

## Run

```bash
poetry run python demos/analytics/analytics.py
```

Expected stdout snippets, in order:

```
[0] Seeded unity.analytics_demo.sales: 5,000 rows
```

```
[1] Revenue by product:
|Phone     |668   |1977      |674179.03    |1009.25        |
```

```
[2] Regional performance:
|South America|1314  |1298625.64|988.3    |26.19       |
```

```
[3] Top 3 customers per region:
|North America|customer_0095|15    |16297.8    |1   |
```

```
[5] Charts saved: demos/analytics/charts/revenue_by_product_and_region.png, demos/analytics/charts/daily_revenue_trend.png
```

## Expected output

- A governed table `unity.analytics_demo.sales` (external Delta, 5,000 rows, deterministic via
  `random.seed(42)`) under `s3://lakehouse/warehouse/analytics/sales`.
- Four analytics result sets (revenue by product, regional share, top-3 customers per region,
  daily trend) printed to stdout.
- Two PNGs in `demos/analytics/charts/`: `revenue_by_product_and_region.png` and
  `daily_revenue_trend.png` (only when matplotlib is installed).

## Teardown

```bash
bash demos/analytics/teardown.sh
```
