# Lakehouse Stack - Databricks Terraform Outputs

# -----------------------------------------------------------------------------
# Catalog Information
# -----------------------------------------------------------------------------

output "catalog_name" {
  description = "Name of the Unity Catalog"
  value       = databricks_catalog.lakehouse.name
}

output "schemas" {
  description = "Medallion architecture schemas"
  value = {
    bronze = databricks_schema.bronze.name
    silver = databricks_schema.silver.name
    gold   = databricks_schema.gold.name
  }
}

# -----------------------------------------------------------------------------
# Storage Information
# -----------------------------------------------------------------------------

output "external_location_name" {
  description = "Name of the external location"
  value       = databricks_external_location.lakehouse.name
}

output "storage_location" {
  description = "Cloud storage location for data"
  value       = var.storage_location
}

# -----------------------------------------------------------------------------
# Compute Information
# -----------------------------------------------------------------------------

output "interactive_cluster_id" {
  description = "ID of the interactive cluster (if created)"
  value       = var.create_interactive_cluster ? databricks_cluster.interactive[0].id : null
}

output "interactive_cluster_url" {
  description = "URL to the interactive cluster (if created)"
  value       = var.create_interactive_cluster ? "${var.databricks_host}/#/setting/clusters/${databricks_cluster.interactive[0].id}/configuration" : null
}

output "sql_warehouse_id" {
  description = "ID of the SQL Warehouse (if created)"
  value       = var.create_sql_warehouse ? databricks_sql_endpoint.analytics[0].id : null
}

output "sql_warehouse_jdbc_url" {
  description = "JDBC URL for SQL Warehouse (if created)"
  value       = var.create_sql_warehouse ? databricks_sql_endpoint.analytics[0].jdbc_url : null
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Job Information
# -----------------------------------------------------------------------------

output "bronze_etl_job_id" {
  description = "ID of the bronze ETL job (if created)"
  value       = var.create_etl_jobs ? databricks_job.bronze_etl[0].id : null
}

output "silver_etl_job_id" {
  description = "ID of the silver ETL job (if created)"
  value       = var.create_etl_jobs ? databricks_job.silver_etl[0].id : null
}

# -----------------------------------------------------------------------------
# Connection Information
# -----------------------------------------------------------------------------

output "databricks_host" {
  description = "Databricks workspace URL"
  value       = var.databricks_host
}

output "secret_scope_name" {
  description = "Name of the secret scope"
  value       = databricks_secret_scope.lakehouse.name
}

# -----------------------------------------------------------------------------
# Configuration Snippets
# -----------------------------------------------------------------------------

output "spark_conf_snippet" {
  description = "Spark configuration for connecting to the catalog"
  value       = <<-EOT
    # Add to your Spark session configuration
    spark.sql.catalog.${var.catalog_name}=org.apache.iceberg.spark.SparkCatalog
    spark.sql.catalog.${var.catalog_name}.type=hadoop
    spark.sql.catalog.${var.catalog_name}.warehouse=${var.storage_location}
  EOT
}

output "notebook_connection_snippet" {
  description = "Python code for connecting to tables in notebooks"
  value       = <<-EOT
    # Read from bronze layer
    bronze_df = spark.table("${var.catalog_name}.bronze.your_table")

    # Read from silver layer
    silver_df = spark.table("${var.catalog_name}.silver.your_table")

    # Read from gold layer
    gold_df = spark.table("${var.catalog_name}.gold.your_table")

    # Write to Iceberg table
    df.writeTo("${var.catalog_name}.bronze.new_table").createOrReplace()
  EOT
}

output "env_file_content" {
  description = "Content for .env file (for local development reference)"
  sensitive   = true
  value       = <<-EOT
    # Databricks Configuration
    DATABRICKS_HOST=${var.databricks_host}
    DATABRICKS_TOKEN=<your-token>

    # Unity Catalog
    CATALOG_NAME=${var.catalog_name}
    STORAGE_LOCATION=${var.storage_location}

    # SQL Warehouse (for BI tools)
    ${var.create_sql_warehouse ? "SQL_WAREHOUSE_ID=${databricks_sql_endpoint.analytics[0].id}" : "# SQL Warehouse not created"}

    # Secret Scope
    SECRET_SCOPE=${databricks_secret_scope.lakehouse.name}
  EOT
}

# -----------------------------------------------------------------------------
# Quick Reference
# -----------------------------------------------------------------------------

output "quick_reference" {
  description = "Quick reference for common operations"
  value       = <<-EOT

    ============================================
    Lakehouse Databricks Deployment - Quick Reference
    ============================================

    Workspace: ${var.databricks_host}

    Unity Catalog: ${var.catalog_name}
      - bronze: Raw data layer
      - silver: Cleaned data layer
      - gold: Business-ready layer

    Storage: ${var.storage_location}

    ${var.create_interactive_cluster ? "Interactive Cluster: ${databricks_cluster.interactive[0].cluster_name}" : "Interactive Cluster: Not created"}
    ${var.create_sql_warehouse ? "SQL Warehouse: ${databricks_sql_endpoint.analytics[0].name}" : "SQL Warehouse: Not created"}

    Common Commands:
    ----------------
    # List tables in bronze schema
    SHOW TABLES IN ${var.catalog_name}.bronze;

    # Query a table
    SELECT * FROM ${var.catalog_name}.bronze.your_table LIMIT 10;

    # Time travel query
    SELECT * FROM ${var.catalog_name}.bronze.your_table VERSION AS OF 1;

    ============================================
  EOT
}
