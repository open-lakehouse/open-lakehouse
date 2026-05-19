# Test Data Generation

Generate realistic food delivery order data for testing batch and streaming workflows.

## Overview

The test data generator creates order lifecycle events inspired by [Casper's Kitchens](https://github.com/databricks-solutions/caspers-kitchens). It simulates a ghost kitchen food delivery platform with realistic timing, chaos injection, and configurable scale.

## Quick Start

```bash
# Generate 7 days of data
./lakehouse testdata generate --days 7

# Load into Iceberg tables
./lakehouse testdata load

# Stream to Kafka at 60x speed
./lakehouse testdata stream --speed 60
```

## Commands

### generate

Create order events as Parquet files.

```bash
./lakehouse testdata generate                  # 90 days (~7GB)
./lakehouse testdata generate --days 7         # 7 days (~500MB)
./lakehouse testdata generate --days 1         # 1 day (~70MB)
./lakehouse testdata generate --seed 42        # Reproducible
```

Output:
- `data/dimensions/` - Dimension tables (brands, items, etc.)
- `data/events/orders_Nd.parquet` - Event data
- `data/load_to_iceberg.py` - Generated load script

### load

Load generated data into Iceberg tables.

```bash
./lakehouse testdata load
```

Creates tables in `iceberg.bronze.*` namespace.

### stream

Stream events to Kafka in simulated real-time.

```bash
./lakehouse testdata stream                    # Real-time
./lakehouse testdata stream --speed 60         # 60x (1 min = 1 hour)
./lakehouse testdata stream --speed 3600       # 3600x (1 sec = 1 hour)
```

### stats

Show dataset statistics.

```bash
./lakehouse testdata stats
```

### clean

Remove all generated data.

```bash
./lakehouse testdata clean
```

## Data Schema

### Dimension Tables

| Table | Records | Description |
|-------|---------|-------------|
| `dim_brands` | 20 | Ghost kitchen brands |
| `dim_items` | 160 | Menu items (8 per brand) |
| `dim_categories` | 10 | Food categories |
| `dim_locations` | 4 | Delivery cities |

### Event Schema

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | string | UUID |
| `event_type` | string | Lifecycle event type |
| `ts` | string | ISO 8601 timestamp |
| `order_id` | string | UUID |
| `location_id` | int | FK to dim_locations |
| `sequence` | int | Event order in lifecycle |
| `body` | string | JSON payload |

### Event Types

Order lifecycle progression:

```
order_created       # Customer places order
    ↓
kitchen_started     # Kitchen begins preparation
    ↓
kitchen_finished    # Food ready for pickup
    ↓
order_ready         # Packaged for driver
    ↓
driver_arrived      # Driver at restaurant
    ↓
driver_picked_up    # Driver has order
    ↓
driver_ping (1-5x)  # Driver location updates
    ↓
delivered           # Order complete
```

## Chaos Injection

The generator includes configurable data quality issues for testing resilience:

| Issue | Description |
|-------|-------------|
| Null values | Random nulls in non-key fields |
| Late events | Events arriving out of order |
| Duplicates | Duplicate event IDs |
| Malformed JSON | Invalid JSON in body field |

## Data Volumes

Approximate sizes by days:

| Days | Orders | Events | File Size |
|------|--------|--------|-----------|
| 1 | ~38K | ~1M | ~70MB |
| 7 | ~266K | ~7M | ~500MB |
| 30 | ~1.1M | ~30M | ~2GB |
| 90 | ~3.4M | ~92M | ~7GB |

## Example Workflows

### Batch Processing

```bash
# Generate data
./lakehouse testdata generate --days 30

# Load to Iceberg
./lakehouse testdata load

# Query with Spark
docker exec -it spark-master-41 /opt/spark/bin/spark-sql \
  -e "SELECT event_type, COUNT(*) FROM iceberg.bronze.orders GROUP BY 1"
```

### Streaming Pipeline

Terminal 1:
```bash
./lakehouse testdata stream --speed 60
```

Terminal 2:
```bash
./lakehouse consumer
```

### Reproducible Testing

```bash
# Same seed = same data
./lakehouse testdata generate --days 7 --seed 12345
./lakehouse testdata clean
./lakehouse testdata generate --days 7 --seed 12345  # Identical output
```

## Module Structure

```
scripts/testdata/
├── __init__.py     # Main entry point
├── __main__.py     # CLI handler
├── config.py       # Configuration dataclasses
├── dimensions.py   # Dimension table generators
├── events.py       # Order lifecycle event generator
├── chaos.py        # Data quality issue injection
├── exporter.py     # Parquet batch export
└── producer.py     # Kafka streaming producer
```

## Kafka Topics

When streaming, events are published to:
- Topic: `orders` (configurable)
- Key: `order_id`
- Value: JSON event

## See Also

- [Streaming Guide](streaming.md)
- [CLI Reference](cli-reference.md)
