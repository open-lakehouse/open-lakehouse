# Databricks Deployment Guide

Deploy the lakehouse stack to Databricks for production-grade managed Spark with native Iceberg support.

## Architecture Comparison

| Local Component | Databricks Equivalent | Notes |
|-----------------|----------------------|-------|
| PostgreSQL 16 | Unity Catalog | Managed metastore, or external JDBC |
| SeaweedFS | Cloud Storage (S3/ADLS/GCS) | Native cloud storage |
| Spark 4.x | Databricks Runtime 15+ | Managed Spark with optimizations |
| Kafka | Partner Connect (Confluent) | Or external Kafka/EventHubs |
| Docker containers | - | Not needed |

## Databricks Architecture

```
                    ┌─────────────────────────────────────┐
                    │       Databricks Workspace          │
                    │                                     │
┌───────────┐       │  ┌─────────────┐  ┌─────────────┐  │
│  Client   │───────┼──│  Clusters   │  │  SQL        │  │
│  (Notebook│       │  │  (Spark)    │  │  Warehouse  │  │
│   or API) │       │  └──────┬──────┘  └──────┬──────┘  │
└───────────┘       │         │                │         │
                    │         ▼                ▼         │
                    │  ┌─────────────────────────────┐   │
                    │  │       Unity Catalog          │   │
                    │  │  (Iceberg/Delta metadata)    │   │
                    │  └──────────────┬──────────────┘   │
                    │                 │                   │
                    └─────────────────┼───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │   Cloud Storage (S3/ADLS/GCS)       │
                    │   - Iceberg table data              │
                    │   - Parquet files                   │
                    └─────────────────────────────────────┘
```

## Databricks Options

| Tier | Best For | Compute |
|------|----------|---------|
| **Community Edition** | Learning, free tier | Single small cluster |
| **Standard** | Teams, production | Clusters + Jobs |
| **Premium** | Enterprise, Unity Catalog | Full feature set |

**Unity Catalog** (Premium) is recommended for proper Iceberg catalog management.

## Cost Estimates

| Resource | Configuration | Monthly Cost |
|----------|---------------|--------------|
| DBU (All-Purpose) | 2 DBU × 40 hrs/week | ~$200 |
| DBU (Jobs) | 1 DBU × 100 jobs | ~$50 |
| DBU (SQL Warehouse) | Serverless, light use | ~$100 |
| Cloud Storage | 100GB S3/ADLS | ~$3 |
| **Development Total** | | **~$350/month** |

**Cost Optimization Tips:**
- Use Jobs clusters instead of All-Purpose (50% cheaper)
- Enable auto-termination (default: 120 minutes)
- Use Spot/Preemptible instances for non-critical workloads
- SQL Serverless scales to zero when idle

## Setup Instructions

### Prerequisites

```bash
# Install Databricks CLI
pip install databricks-cli

# Or using Homebrew (macOS)
brew tap databricks/tap
brew install databricks

# Configure authentication
databricks configure --token
# Enter: Databricks host URL and personal access token
```

### 1. Create Databricks Workspace

#### AWS
```bash
# Via AWS Console or Terraform
# See: https://docs.databricks.com/administration-guide/cloud-configurations/aws/
```

#### Azure
```bash
# Via Azure CLI
az databricks workspace create \
  --resource-group lakehouse-rg \
  --name lakehouse-workspace \
  --location eastus \
  --sku premium
```

#### GCP
```bash
# Via GCP Console
# See: https://docs.databricks.com/administration-guide/cloud-configurations/gcp/
```

### 2. Configure Unity Catalog (Recommended)

Unity Catalog provides centralized governance and native Iceberg support.

```sql
-- In Databricks SQL or notebook

-- Create catalog
CREATE CATALOG IF NOT EXISTS lakehouse;

-- Create schemas (medallion architecture)
CREATE SCHEMA IF NOT EXISTS lakehouse.bronze;
CREATE SCHEMA IF NOT EXISTS lakehouse.silver;
CREATE SCHEMA IF NOT EXISTS lakehouse.gold;

-- Grant permissions
GRANT USE CATALOG ON CATALOG lakehouse TO `data-engineers`;
GRANT USE SCHEMA ON SCHEMA lakehouse.bronze TO `data-engineers`;
GRANT CREATE TABLE ON SCHEMA lakehouse.bronze TO `data-engineers`;
```

### 3. Create External Storage Location

```sql
-- Create storage credential (AWS example)
CREATE STORAGE CREDENTIAL lakehouse_cred
WITH (
  AWS_IAM_ROLE = 'arn:aws:iam::123456789:role/databricks-storage-role'
);

-- Create external location
CREATE EXTERNAL LOCATION lakehouse_storage
URL 's3://your-lakehouse-bucket/warehouse'
WITH (STORAGE CREDENTIAL lakehouse_cred);
```

### 4. Create Compute Resources

#### All-Purpose Cluster (Interactive)

```json
{
  "cluster_name": "lakehouse-dev",
  "spark_version": "15.4.x-scala2.12",
  "node_type_id": "m5.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 60,
  "spark_conf": {
    "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.iceberg.type": "hadoop",
    "spark.sql.catalog.iceberg.warehouse": "s3://your-lakehouse-bucket/warehouse"
  },
  "data_security_mode": "USER_ISOLATION"
}
```

Create via CLI:
```bash
databricks clusters create --json-file cluster-config.json
```

#### Jobs Cluster (Scheduled)

```bash
# Create job with dedicated cluster
databricks jobs create --json '{
  "name": "lakehouse-etl-daily",
  "tasks": [{
    "task_key": "bronze_to_silver",
    "spark_python_task": {
      "python_file": "dbfs:/scripts/bronze_to_silver.py"
    },
    "new_cluster": {
      "spark_version": "15.4.x-scala2.12",
      "node_type_id": "m5.xlarge",
      "num_workers": 2
    }
  }],
  "schedule": {
    "quartz_cron_expression": "0 0 6 * * ?",
    "timezone_id": "UTC"
  }
}'
```

#### SQL Warehouse (Analytics)

```bash
databricks sql warehouses create --json '{
  "name": "lakehouse-analytics",
  "cluster_size": "Small",
  "min_num_clusters": 1,
  "max_num_clusters": 2,
  "auto_stop_mins": 15,
  "warehouse_type": "PRO",
  "enable_serverless_compute": true
}'
```

## Working with Iceberg Tables

### Create Iceberg Tables

```python
# In Databricks notebook

# Option 1: Using Unity Catalog (Recommended)
spark.sql("""
    CREATE TABLE lakehouse.bronze.orders (
        order_id STRING,
        customer_id STRING,
        order_date DATE,
        total DECIMAL(10,2)
    ) USING ICEBERG
    PARTITIONED BY (days(order_date))
""")

# Option 2: Using external Iceberg catalog
spark.sql("""
    CREATE TABLE iceberg.bronze.orders (
        order_id STRING,
        customer_id STRING,
        order_date DATE,
        total DECIMAL(10,2)
    ) USING ICEBERG
    PARTITIONED BY (days(order_date))
    LOCATION 's3://your-lakehouse-bucket/warehouse/bronze/orders'
""")
```

### Read/Write Operations

```python
# Write to Iceberg
df = spark.read.parquet("/mnt/data/raw_orders")
df.writeTo("lakehouse.bronze.orders").append()

# Read from Iceberg
orders = spark.table("lakehouse.bronze.orders")

# Time travel
orders_yesterday = spark.read \
    .option("as-of-timestamp", "2024-01-01 00:00:00") \
    .table("lakehouse.bronze.orders")

# Snapshot query
orders_snapshot = spark.read \
    .option("snapshot-id", 1234567890) \
    .table("lakehouse.bronze.orders")
```

### Schema Evolution

```python
# Add column
spark.sql("ALTER TABLE lakehouse.bronze.orders ADD COLUMN status STRING")

# Rename column
spark.sql("ALTER TABLE lakehouse.bronze.orders RENAME COLUMN total TO order_total")
```

## Migrating from Local

### 1. Export Local Data

```bash
# On local machine
./lakehouse testdata generate --days 30

# Export to parquet
spark-submit scripts/export-to-parquet.py \
  --source iceberg.bronze.orders \
  --output ./export/orders/
```

### 2. Upload to Cloud Storage

```bash
# AWS
aws s3 cp ./export/ s3://your-lakehouse-bucket/import/ --recursive

# Azure
az storage blob upload-batch -d import -s ./export/ --account-name youraccount

# GCP
gsutil -m cp -r ./export/ gs://your-lakehouse-bucket/import/
```

### 3. Import into Databricks

```python
# In Databricks notebook

# Read exported parquet
raw_df = spark.read.parquet("s3://your-lakehouse-bucket/import/orders/")

# Write to Iceberg table
raw_df.writeTo("lakehouse.bronze.orders").createOrReplace()

# Verify
spark.table("lakehouse.bronze.orders").count()
```

### 4. Migrate PySpark Scripts

Local script:
```python
# Local: scripts/01-basics.py
spark = SparkSession.builder \
    .appName("LocalApp") \
    .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.iceberg.type", "jdbc") \
    .config("spark.sql.catalog.iceberg.uri", "jdbc:postgresql://localhost:5432/iceberg_catalog") \
    .getOrCreate()

df = spark.table("iceberg.bronze.orders")
```

Databricks version:
```python
# Databricks: notebooks/01-basics
# SparkSession is pre-configured, no builder needed
# Unity Catalog is default

df = spark.table("lakehouse.bronze.orders")
```

## Streaming with Databricks

### Kafka Integration

```python
# Read from Kafka (external cluster)
kafka_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka.example.com:9092") \
    .option("subscribe", "orders") \
    .option("startingOffsets", "latest") \
    .load()

# Parse and write to Iceberg
from pyspark.sql import functions as f

parsed = kafka_df.select(
    f.from_json(
        f.col("value").cast("string"),
        "order_id STRING, customer_id STRING, total DOUBLE, ts TIMESTAMP"
    ).alias("data")
).select("data.*")

query = parsed.writeStream \
    .format("iceberg") \
    .outputMode("append") \
    .option("path", "lakehouse.bronze.orders_stream") \
    .option("checkpointLocation", "/checkpoints/orders") \
    .trigger(processingTime="1 minute") \
    .start()
```

### Event Hubs (Azure)

```python
# Azure Event Hubs integration
eh_df = spark.readStream \
    .format("eventhubs") \
    .options(**{
        "eventhubs.connectionString": dbutils.secrets.get("keyvault", "eh-connection"),
        "eventhubs.consumerGroup": "$Default"
    }) \
    .load()
```

### Auto Loader (Recommended)

Auto Loader is Databricks' optimized streaming file ingestion:

```python
# Stream from cloud storage
df = spark.readStream \
    .format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .option("cloudFiles.schemaLocation", "/checkpoints/schema/orders") \
    .load("s3://your-bucket/raw/orders/")

# Write to Iceberg
df.writeStream \
    .format("iceberg") \
    .outputMode("append") \
    .option("path", "lakehouse.bronze.orders") \
    .option("checkpointLocation", "/checkpoints/orders") \
    .trigger(availableNow=True) \
    .start()
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/databricks-deploy.yml
name: Deploy to Databricks

on:
  push:
    branches: [main]
    paths: ['notebooks/**', 'jobs/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Databricks CLI
        run: pip install databricks-cli

      - name: Configure Databricks
        run: |
          echo "[DEFAULT]" > ~/.databrickscfg
          echo "host = ${{ secrets.DATABRICKS_HOST }}" >> ~/.databrickscfg
          echo "token = ${{ secrets.DATABRICKS_TOKEN }}" >> ~/.databrickscfg

      - name: Deploy notebooks
        run: |
          databricks workspace import_dir ./notebooks /Repos/production/lakehouse --overwrite

      - name: Update jobs
        run: |
          databricks jobs reset --job-id ${{ secrets.ETL_JOB_ID }} --json-file jobs/etl-job.json
```

### Databricks Asset Bundles (DABs)

```yaml
# databricks.yml
bundle:
  name: lakehouse-etl

workspace:
  host: https://your-workspace.cloud.databricks.com

resources:
  jobs:
    bronze_etl:
      name: "Bronze ETL"
      tasks:
        - task_key: ingest
          notebook_task:
            notebook_path: ./notebooks/bronze_ingest.py

environments:
  dev:
    workspace:
      host: https://dev.cloud.databricks.com
  prod:
    workspace:
      host: https://prod.cloud.databricks.com
```

Deploy:
```bash
databricks bundle deploy -e prod
```

## Monitoring

### Built-in Monitoring

- **Cluster Metrics**: Memory, CPU, disk usage
- **Query History**: SQL Warehouse query performance
- **Job Runs**: Success/failure, duration, costs

### Ganglia Metrics (Clusters)

Access via cluster UI → Metrics tab

### Custom Logging

```python
# In notebooks
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lakehouse")

logger.info(f"Processed {df.count()} records")
```

### Alerts

```bash
# Create alert on job failure
databricks jobs create --json '{
  "name": "lakehouse-etl",
  "email_notifications": {
    "on_failure": ["team@example.com"]
  },
  "webhook_notifications": {
    "on_failure": [{
      "id": "slack-webhook-id"
    }]
  }
}'
```

## Security Best Practices

### Secrets Management

```bash
# Create secret scope
databricks secrets create-scope --scope lakehouse

# Add secrets
databricks secrets put --scope lakehouse --key postgres-password
databricks secrets put --scope lakehouse --key kafka-api-key
```

Use in code:
```python
password = dbutils.secrets.get(scope="lakehouse", key="postgres-password")
```

### Table ACLs (Unity Catalog)

```sql
-- Grant read access
GRANT SELECT ON TABLE lakehouse.gold.daily_metrics TO `analysts`;

-- Grant write access
GRANT INSERT, UPDATE ON TABLE lakehouse.silver.orders TO `data-engineers`;

-- Row-level security
CREATE ROW ACCESS POLICY region_filter
AS (region STRING)
RETURN region = current_user_region();

ALTER TABLE lakehouse.gold.sales SET ROW ACCESS POLICY region_filter ON (region);
```

## Cleanup

```bash
# Delete cluster
databricks clusters permanent-delete --cluster-id <cluster-id>

# Delete job
databricks jobs delete --job-id <job-id>

# Delete SQL Warehouse
databricks sql warehouses delete --id <warehouse-id>

# Delete Unity Catalog objects
# (In SQL)
# DROP TABLE lakehouse.bronze.orders;
# DROP SCHEMA lakehouse.bronze;
# DROP CATALOG lakehouse;
```

## Comparison: Local vs Databricks

| Feature | Local Stack | Databricks |
|---------|-------------|------------|
| Setup time | 30 minutes | 1 hour |
| Cost | $0 (hardware only) | $350+/month |
| Scaling | Limited by hardware | Auto-scale |
| Maintenance | Self-managed | Managed |
| Collaboration | Git-based | Notebooks + Git |
| Governance | Manual | Unity Catalog |
| Performance | Good | Optimized (Photon) |

## Terraform Deployment

Use the included Terraform templates for automated infrastructure setup:

```bash
cd terraform-databricks
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform plan
terraform apply
```

See [terraform-databricks/README.md](../../terraform-databricks/README.md) for detailed configuration options.

## Next Steps

1. [Databricks Documentation](https://docs.databricks.com/)
2. [Unity Catalog Guide](https://docs.databricks.com/data-governance/unity-catalog/)
3. [Iceberg on Databricks](https://docs.databricks.com/delta/iceberg.html)
4. [Databricks Asset Bundles](https://docs.databricks.com/dev-tools/bundles/)
