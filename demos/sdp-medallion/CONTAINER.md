# Reproducible medallion demo - laptop container

A thin, data-free container that builds a **bronze -> silver -> gold** medallion of
**Delta tables in Unity Catalog**, running on the shared remote Spark cluster.
Any laptop with Docker can reproduce it; the only per-user secret is a UC token.

## What runs where

```
this container (laptop)          remote (Scott's AWS, us-west-2)
---------------------            ------------------------------
pyspark Connect client  --TLS-- connect.openlakehousedemos.dev  (Spark compute)
(no JVM, no data)                uc.openlakehousedemos.dev        (Unity Catalog)
                                 s3://uc-quickstart-.../medallion-demo/raw/ (real data)
```

The container holds **no data and no AWS creds** - the remote cluster reads the
545 MB of real order events from S3 and writes the Delta tables to UC. Each
laptop just submits the graph and authenticates with its own UC token.

## Prereqs
- Docker
- A valid **UC bearer token** (a full JWT - ~650-800 chars, 3 dot-separated
  segments). Save it to `~/.uc_token`.

## Build
```bash
docker build -t openlakehouse-medallion demos/sdp-medallion
```

## Run
```bash
# Build the full medallion (bronze + silver + gold) on the remote cluster:
docker run --rm -e UC_TOKEN="$(cat ~/.uc_token)" openlakehouse-medallion

# Read-only: list what's already registered in unity.* (no writes):
docker run --rm -e UC_TOKEN="$(cat ~/.uc_token)" openlakehouse-medallion --show
```

Expected tail:
```
gold.brand_summary (top brands by revenue):
+--------+------------------+------------+-------------+...
|brand_id|brand_name        |total_orders|total_revenue|...
```

## Tables produced (in the `unity` catalog)
| Layer | Table | What |
|-------|-------|------|
| bronze | `dim_brands/items/categories/locations` | dimensions |
| bronze | `orders` | raw delivery events, timestamp-parsed |
| silver | `orders_enriched` | parsed JSON body, item counts, time features, city join |
| silver | `order_lifecycle` | one row/order: kitchen + delivery durations from the event pivot |
| gold | `hourly_metrics` | orders/revenue/AOV per hour*location |
| gold | `delivery_performance` | avg + p50/p95 kitchen & delivery times |
| gold | `brand_summary` | revenue/orders/AOV per brand |

## Notes
- **Token model is per-user**: each laptop passes its own `UC_TOKEN`. Nothing
  shared but the catalog + storage - ideal for N laptops.
- The transforms are sourced from `lakehouse-stack`'s `pipeline_spark41.py`,
  retargeted from Iceberg to Unity Catalog Delta and authored in an SDP-style
  declarative graph (functions return DataFrames; deps inferred; topo-executed),
  but executed on the **remote** cluster (the real `spark-pipelines` runtime
  can't target a remote Connect server - it spawns its own local Spark).
- To re-stage the raw data (one-time, already done): upload
  `lakehouse-stack/data/events/orders_7d.parquet` and `data/dimensions/*.parquet`
  to `s3://uc-quickstart-207734640204-usw2/medallion-demo/raw/{orders,dimensions}/`.
