variable "aws_region" {
  type        = string
  description = "AWS region for ECS, ECR, ALB, Secrets Manager, and Route 53/ACM calls."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for created resource names (cluster, service, role, ALB)."
  default     = "mlflow-ecs"
}

# ----- Image ----------------------------------------------------------------
variable "ecr_repo_name" {
  type        = string
  description = "ECR repository holding the MLflow image (created by scripts/terraform/mlflow-ecr-push.sh)."
  default     = "open-lakehouse-mlflow"
}

variable "image_tag" {
  type        = string
  description = "Image tag to deploy (e.g. v0.1.0)."
  default     = "v0.1.0"
}

# ----- Networking -----------------------------------------------------------
variable "vpc_id" {
  type        = string
  description = "VPC to deploy into. Empty string uses the account's default VPC."
  default     = ""
}

variable "subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for the ALB and the Fargate task. Empty uses the default VPC's subnets."
  default     = []
}

# ----- Task sizing ----------------------------------------------------------
variable "cpu" {
  type        = number
  description = "Fargate CPU units for the MLflow task (1 vCPU = 1024)."
  default     = 1024
}

variable "memory" {
  type        = number
  description = "Fargate memory (MiB) for the MLflow task. Must be a valid pair with cpu."
  default     = 2048
}

variable "desired_count" {
  type        = number
  description = "Number of MLflow tasks. The tracking server scales horizontally behind the ALB; all replicas share the same Postgres backend."
  default     = 1
}

variable "mlflow_port" {
  type        = number
  description = "Port the MLflow tracking server binds to (and the ALB target group forwards to)."
  default     = 5000
}

# ----- Backend store (existing PostgreSQL) ----------------------------------
variable "pg_host" {
  type        = string
  description = "Hostname of the existing PostgreSQL server that backs the tracking store."
}

variable "pg_port" {
  type        = number
  description = "Port of the existing PostgreSQL server."
  default     = 5432
}

variable "pg_database" {
  type        = string
  description = "PostgreSQL database name MLflow persists to (must already exist, or be auto-provisioned by supplying superuser creds)."
  default     = "mlflow"
}

variable "pg_user" {
  type        = string
  description = "PostgreSQL role MLflow connects as. When skip_provision is false, this role also performs provisioning, so it must hold CREATEDB (and CREATEROLE if the role itself must be created)."
  default     = "mlflow"
}

variable "pg_admin_db" {
  type        = string
  description = "Maintenance database the role connects to in order to run CREATE DATABASE during provisioning. Vanilla Postgres uses \"postgres\"; Databricks Lakebase uses \"databricks_postgres\". Only used when skip_provision is false."
  default     = "postgres"
}

variable "pg_password_secret_arn" {
  type        = string
  description = "ARN of the AWS Secrets Manager secret (or SSM parameter) holding the PostgreSQL password for pg_user. Injected into the container as MLFLOW_PG_PASS."
}

variable "pg_sslmode" {
  type        = string
  description = "libpq sslmode for the backend store connection. Set to \"require\" for managed Postgres that mandates TLS (e.g. Databricks Lakebase). Empty disables the flag."
  default     = "require"

  validation {
    condition     = contains(["", "disable", "allow", "prefer", "require", "verify-ca", "verify-full"], var.pg_sslmode)
    error_message = "pg_sslmode must be one of: \"\", disable, allow, prefer, require, verify-ca, verify-full."
  }
}

variable "skip_provision" {
  type        = bool
  description = "Skip role/database auto-provisioning. Keep true for managed/external Postgres (the role + db already exist and there is no reachable superuser)."
  default     = true
}

# ----- Artifact store (existing S3 bucket) ----------------------------------
variable "artifact_bucket" {
  type        = string
  description = "Existing S3 bucket name for MLflow artifacts. Access is granted to the task IAM role; no static keys are used."
}

variable "artifact_prefix" {
  type        = string
  description = "Key prefix within artifact_bucket for MLflow artifacts (no leading/trailing slash)."
  default     = "mlflow-artifacts"
}

# ----- Tracking server security (MLflow 3.5+ uvicorn middleware) ------------
variable "allowed_hosts" {
  type        = string
  description = "Comma-separated Host header allow-list passed to --allowed-hosts (DNS-rebinding protection). Empty falls back to the public FQDN / ALB DNS name."
  default     = ""
}

variable "cors_allowed_origins" {
  type        = string
  description = "Comma-separated origins passed to --cors-allowed-origins. Empty falls back to the public https origin when a domain is configured."
  default     = ""
}

# ----- DNS / TLS (optional) -------------------------------------------------
variable "domain_name" {
  type        = string
  description = "Public FQDN for the tracking server over HTTPS (e.g. mlflow.openlakehousedemos.dev). Empty = HTTP-only on the ALB DNS name. Requires hosted_zone_id."
  default     = ""
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID that owns domain_name (used for ACM DNS validation and the alias record)."
  default     = ""
}

variable "cert_domain_name" {
  type        = string
  description = "Domain for the ACM cert. Empty = use domain_name. Set a wildcard like \"*.openlakehousedemos.dev\" to reuse one cert across subdomains."
  default     = ""
}

# ----- Misc -----------------------------------------------------------------
variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention for the MLflow task."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to created resources."
  default     = { project = "open-lakehouse" }
}
