# Lakehouse Stack - Databricks Infrastructure
# Terraform configuration for deploying the lakehouse on Databricks
#
# Supports: AWS, Azure, GCP
# Prerequisites: Databricks workspace must already exist

terraform {
  required_version = ">= 1.0"
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.50"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration
# -----------------------------------------------------------------------------

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

provider "aws" {
  region = var.aws_region
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "databricks_current_user" "me" {}

data "databricks_spark_version" "latest" {
  long_term_support = true
}

data "databricks_node_type" "smallest" {
  local_disk = true
}

# -----------------------------------------------------------------------------
# Unity Catalog Resources
# -----------------------------------------------------------------------------

# Storage Credential (AWS)
resource "databricks_storage_credential" "lakehouse" {
  count = var.cloud_provider == "aws" ? 1 : 0
  name  = "${var.project_name}-storage-credential"

  aws_iam_role {
    role_arn = var.aws_iam_role_arn
  }

  comment = "Storage credential for lakehouse data lake"
}

# Storage Credential (Azure)
resource "databricks_storage_credential" "lakehouse_azure" {
  count = var.cloud_provider == "azure" ? 1 : 0
  name  = "${var.project_name}-storage-credential"

  azure_managed_identity {
    access_connector_id = var.azure_access_connector_id
  }

  comment = "Storage credential for lakehouse data lake"
}

# External Location
resource "databricks_external_location" "lakehouse" {
  name = "${var.project_name}-external-location"
  url  = var.storage_location

  credential_name = var.cloud_provider == "aws" ? databricks_storage_credential.lakehouse[0].name : databricks_storage_credential.lakehouse_azure[0].name

  comment = "External location for lakehouse warehouse"
}

# Unity Catalog - Catalog
resource "databricks_catalog" "lakehouse" {
  name    = var.catalog_name
  comment = "Lakehouse data catalog with medallion architecture"

  properties = {
    purpose     = "lakehouse"
    environment = var.environment
  }
}

# Unity Catalog - Schemas (Medallion Architecture)
resource "databricks_schema" "bronze" {
  catalog_name = databricks_catalog.lakehouse.name
  name         = "bronze"
  comment      = "Raw data layer - ingested data with minimal transformation"

  properties = {
    layer = "bronze"
  }
}

resource "databricks_schema" "silver" {
  catalog_name = databricks_catalog.lakehouse.name
  name         = "silver"
  comment      = "Cleaned data layer - validated and deduplicated"

  properties = {
    layer = "silver"
  }
}

resource "databricks_schema" "gold" {
  catalog_name = databricks_catalog.lakehouse.name
  name         = "gold"
  comment      = "Business-ready data layer - aggregated and enriched"

  properties = {
    layer = "gold"
  }
}

# -----------------------------------------------------------------------------
# Compute Resources
# -----------------------------------------------------------------------------

# All-Purpose Cluster (Interactive Development)
resource "databricks_cluster" "interactive" {
  count = var.create_interactive_cluster ? 1 : 0

  cluster_name            = "${var.project_name}-interactive"
  spark_version           = data.databricks_spark_version.latest.id
  node_type_id            = var.interactive_cluster_node_type
  autotermination_minutes = var.cluster_autotermination_minutes
  data_security_mode      = "USER_ISOLATION"

  autoscale {
    min_workers = var.interactive_cluster_min_workers
    max_workers = var.interactive_cluster_max_workers
  }

  spark_conf = {
    # Iceberg configuration
    "spark.sql.catalog.${var.catalog_name}"           = "org.apache.iceberg.spark.SparkCatalog"
    "spark.sql.catalog.${var.catalog_name}.type"      = "hadoop"
    "spark.sql.catalog.${var.catalog_name}.warehouse" = var.storage_location

    # Performance optimizations
    "spark.sql.adaptive.enabled"                     = "true"
    "spark.sql.adaptive.coalescePartitions.enabled"  = "true"
    "spark.databricks.delta.preview.enabled"         = "true"
  }

  custom_tags = {
    Project     = var.project_name
    Environment = var.environment
    Purpose     = "interactive"
  }

  library {
    pypi {
      package = "pyiceberg"
    }
  }
}

# SQL Warehouse (Analytics)
resource "databricks_sql_endpoint" "analytics" {
  count = var.create_sql_warehouse ? 1 : 0

  name                      = "${var.project_name}-analytics"
  cluster_size              = var.sql_warehouse_size
  min_num_clusters          = 1
  max_num_clusters          = var.sql_warehouse_max_clusters
  auto_stop_mins            = var.sql_warehouse_auto_stop_mins
  enable_serverless_compute = var.sql_warehouse_serverless

  warehouse_type = "PRO"

  tags {
    custom_tags {
      key   = "Project"
      value = var.project_name
    }
    custom_tags {
      key   = "Environment"
      value = var.environment
    }
  }
}

# -----------------------------------------------------------------------------
# Jobs
# -----------------------------------------------------------------------------

# Bronze ETL Job
resource "databricks_job" "bronze_etl" {
  count = var.create_etl_jobs ? 1 : 0

  name = "${var.project_name}-bronze-etl"

  task {
    task_key = "ingest_raw_data"

    new_cluster {
      spark_version = data.databricks_spark_version.latest.id
      node_type_id  = var.job_cluster_node_type
      num_workers   = var.job_cluster_num_workers

      spark_conf = {
        "spark.sql.catalog.${var.catalog_name}"           = "org.apache.iceberg.spark.SparkCatalog"
        "spark.sql.catalog.${var.catalog_name}.type"      = "hadoop"
        "spark.sql.catalog.${var.catalog_name}.warehouse" = var.storage_location
      }
    }

    notebook_task {
      notebook_path = "${databricks_notebook.bronze_etl[0].path}"
    }
  }

  schedule {
    quartz_cron_expression = var.bronze_etl_schedule
    timezone_id            = var.timezone
  }

  email_notifications {
    on_failure = var.notification_emails
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    Pipeline    = "bronze"
  }
}

# Silver ETL Job
resource "databricks_job" "silver_etl" {
  count = var.create_etl_jobs ? 1 : 0

  name = "${var.project_name}-silver-etl"

  task {
    task_key = "transform_data"

    new_cluster {
      spark_version = data.databricks_spark_version.latest.id
      node_type_id  = var.job_cluster_node_type
      num_workers   = var.job_cluster_num_workers

      spark_conf = {
        "spark.sql.catalog.${var.catalog_name}"           = "org.apache.iceberg.spark.SparkCatalog"
        "spark.sql.catalog.${var.catalog_name}.type"      = "hadoop"
        "spark.sql.catalog.${var.catalog_name}.warehouse" = var.storage_location
      }
    }

    notebook_task {
      notebook_path = "${databricks_notebook.silver_etl[0].path}"
    }

    depends_on {
      task_key = "bronze_complete"
    }
  }

  schedule {
    quartz_cron_expression = var.silver_etl_schedule
    timezone_id            = var.timezone
  }

  email_notifications {
    on_failure = var.notification_emails
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    Pipeline    = "silver"
  }
}

# -----------------------------------------------------------------------------
# Notebooks (Templates)
# -----------------------------------------------------------------------------

resource "databricks_notebook" "bronze_etl" {
  count = var.create_etl_jobs ? 1 : 0

  path     = "/Repos/${var.project_name}/notebooks/bronze_etl"
  language = "PYTHON"
  content_base64 = base64encode(<<-EOT
# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze ETL - Raw Data Ingestion
# MAGIC
# MAGIC This notebook ingests raw data into the bronze layer.

# COMMAND ----------

from pyspark.sql import functions as f

# COMMAND ----------

# Configuration
catalog = "${var.catalog_name}"
schema = "bronze"
source_path = "${var.storage_location}/raw"

# COMMAND ----------

# Read raw data
df = spark.read.format("parquet").load(source_path)

# COMMAND ----------

# Add metadata columns
df_with_metadata = df \
    .withColumn("_ingested_at", f.current_timestamp()) \
    .withColumn("_source_file", f.input_file_name())

# COMMAND ----------

# Write to Iceberg table
df_with_metadata.writeTo(f"{catalog}.{schema}.raw_events").createOrReplace()

# COMMAND ----------

# Verify
spark.table(f"{catalog}.{schema}.raw_events").count()
EOT
  )
}

resource "databricks_notebook" "silver_etl" {
  count = var.create_etl_jobs ? 1 : 0

  path     = "/Repos/${var.project_name}/notebooks/silver_etl"
  language = "PYTHON"
  content_base64 = base64encode(<<-EOT
# Databricks notebook source
# MAGIC %md
# MAGIC # Silver ETL - Data Transformation
# MAGIC
# MAGIC This notebook transforms bronze data into the silver layer.

# COMMAND ----------

from pyspark.sql import functions as f

# COMMAND ----------

# Configuration
catalog = "${var.catalog_name}"
bronze_schema = "bronze"
silver_schema = "silver"

# COMMAND ----------

# Read from bronze
bronze_df = spark.table(f"{catalog}.{bronze_schema}.raw_events")

# COMMAND ----------

# Clean and transform
silver_df = bronze_df \
    .filter(f.col("event_id").isNotNull()) \
    .dropDuplicates(["event_id"]) \
    .withColumn("_processed_at", f.current_timestamp())

# COMMAND ----------

# Write to silver Iceberg table
silver_df.writeTo(f"{catalog}.{silver_schema}.events").createOrReplace()

# COMMAND ----------

# Verify
spark.table(f"{catalog}.{silver_schema}.events").count()
EOT
  )
}

# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------

# Grant access to data engineers group
resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.lakehouse.name

  grant {
    principal  = var.data_engineers_group
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
  }

  grant {
    principal  = var.analysts_group
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT"]
  }
}

resource "databricks_grants" "bronze_schema" {
  schema = "${databricks_catalog.lakehouse.name}.${databricks_schema.bronze.name}"

  grant {
    principal  = var.data_engineers_group
    privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
  }
}

resource "databricks_grants" "silver_schema" {
  schema = "${databricks_catalog.lakehouse.name}.${databricks_schema.silver.name}"

  grant {
    principal  = var.data_engineers_group
    privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
  }

  grant {
    principal  = var.analysts_group
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

resource "databricks_grants" "gold_schema" {
  schema = "${databricks_catalog.lakehouse.name}.${databricks_schema.gold.name}"

  grant {
    principal  = var.data_engineers_group
    privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
  }

  grant {
    principal  = var.analysts_group
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

# -----------------------------------------------------------------------------
# Secret Scope (for external credentials)
# -----------------------------------------------------------------------------

resource "databricks_secret_scope" "lakehouse" {
  name = var.project_name
}

resource "databricks_secret" "kafka_api_key" {
  count        = var.kafka_api_key != "" ? 1 : 0
  key          = "kafka-api-key"
  string_value = var.kafka_api_key
  scope        = databricks_secret_scope.lakehouse.name
}

resource "databricks_secret" "kafka_api_secret" {
  count        = var.kafka_api_secret != "" ? 1 : 0
  key          = "kafka-api-secret"
  string_value = var.kafka_api_secret
  scope        = databricks_secret_scope.lakehouse.name
}
