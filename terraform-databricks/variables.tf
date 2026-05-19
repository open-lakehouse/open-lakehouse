# Lakehouse Stack - Databricks Terraform Variables

# -----------------------------------------------------------------------------
# Databricks Connection
# -----------------------------------------------------------------------------

variable "databricks_host" {
  description = "Databricks workspace URL (e.g., https://xxx.cloud.databricks.com)"
  type        = string
}

variable "databricks_token" {
  description = "Databricks personal access token"
  type        = string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Project Settings
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "lakehouse"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "catalog_name" {
  description = "Name of the Unity Catalog"
  type        = string
  default     = "lakehouse"
}

variable "timezone" {
  description = "Timezone for job schedules"
  type        = string
  default     = "UTC"
}

# -----------------------------------------------------------------------------
# Cloud Provider Settings
# -----------------------------------------------------------------------------

variable "cloud_provider" {
  description = "Cloud provider (aws, azure, gcp)"
  type        = string
  default     = "aws"

  validation {
    condition     = contains(["aws", "azure", "gcp"], var.cloud_provider)
    error_message = "Cloud provider must be aws, azure, or gcp."
  }
}

variable "aws_region" {
  description = "AWS region (if using AWS)"
  type        = string
  default     = "us-west-2"
}

variable "aws_iam_role_arn" {
  description = "ARN of IAM role for storage credential (AWS)"
  type        = string
  default     = ""
}

variable "azure_access_connector_id" {
  description = "Azure Access Connector ID for storage credential"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Storage Settings
# -----------------------------------------------------------------------------

variable "storage_location" {
  description = "Cloud storage location for data (s3://bucket/path, abfss://container@account/path, gs://bucket/path)"
  type        = string
}

# -----------------------------------------------------------------------------
# Interactive Cluster Settings
# -----------------------------------------------------------------------------

variable "create_interactive_cluster" {
  description = "Create an interactive all-purpose cluster"
  type        = bool
  default     = true
}

variable "interactive_cluster_node_type" {
  description = "Node type for interactive cluster"
  type        = string
  default     = "m5.xlarge"  # AWS default, will be adjusted per cloud
}

variable "interactive_cluster_min_workers" {
  description = "Minimum workers for interactive cluster autoscaling"
  type        = number
  default     = 1
}

variable "interactive_cluster_max_workers" {
  description = "Maximum workers for interactive cluster autoscaling"
  type        = number
  default     = 4
}

variable "cluster_autotermination_minutes" {
  description = "Minutes of inactivity before cluster terminates"
  type        = number
  default     = 60
}

# -----------------------------------------------------------------------------
# SQL Warehouse Settings
# -----------------------------------------------------------------------------

variable "create_sql_warehouse" {
  description = "Create a SQL Warehouse for analytics"
  type        = bool
  default     = true
}

variable "sql_warehouse_size" {
  description = "Size of SQL Warehouse (2X-Small, X-Small, Small, Medium, Large, X-Large, 2X-Large, 3X-Large, 4X-Large)"
  type        = string
  default     = "Small"
}

variable "sql_warehouse_max_clusters" {
  description = "Maximum number of clusters for SQL Warehouse"
  type        = number
  default     = 2
}

variable "sql_warehouse_auto_stop_mins" {
  description = "Minutes of inactivity before SQL Warehouse stops"
  type        = number
  default     = 15
}

variable "sql_warehouse_serverless" {
  description = "Enable serverless compute for SQL Warehouse"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# Job Cluster Settings
# -----------------------------------------------------------------------------

variable "create_etl_jobs" {
  description = "Create ETL jobs for medallion architecture"
  type        = bool
  default     = false
}

variable "job_cluster_node_type" {
  description = "Node type for job clusters"
  type        = string
  default     = "m5.xlarge"
}

variable "job_cluster_num_workers" {
  description = "Number of workers for job clusters"
  type        = number
  default     = 2
}

variable "bronze_etl_schedule" {
  description = "Cron schedule for bronze ETL job"
  type        = string
  default     = "0 0 * * * ?"  # Every hour
}

variable "silver_etl_schedule" {
  description = "Cron schedule for silver ETL job"
  type        = string
  default     = "0 30 * * * ?"  # Every hour at :30
}

# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------

variable "data_engineers_group" {
  description = "Databricks group name for data engineers"
  type        = string
  default     = "data-engineers"
}

variable "analysts_group" {
  description = "Databricks group name for analysts"
  type        = string
  default     = "analysts"
}

# -----------------------------------------------------------------------------
# Notifications
# -----------------------------------------------------------------------------

variable "notification_emails" {
  description = "Email addresses for job failure notifications"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# External Services (Optional)
# -----------------------------------------------------------------------------

variable "kafka_api_key" {
  description = "Kafka API key (for streaming jobs)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "kafka_api_secret" {
  description = "Kafka API secret (for streaming jobs)"
  type        = string
  default     = ""
  sensitive   = true
}
