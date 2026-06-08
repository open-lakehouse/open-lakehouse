variable "aws_region" {
  type        = string
  description = "AWS region for ECS, ECR, ALB, NLB, and Route 53/ACM calls."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for created resource names (cluster, services, roles, LBs)."
  default     = "spark-ecs"
}

# ----- Image ----------------------------------------------------------------
variable "ecr_repo_name" {
  type        = string
  description = "ECR repository holding the Spark image (created by scripts/terraform/spark-ecr-push.sh)."
  default     = "open-lakehouse-spark"
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
  description = "Public subnet IDs for the LBs and Fargate tasks. Empty uses the default VPC's subnets."
  default     = []
}

variable "service_discovery_namespace" {
  type        = string
  description = "Cloud Map private DNS namespace for internal master/worker discovery."
  default     = "spark.local"
}

# ----- Cluster sizing -------------------------------------------------------
# Fargate tasks are a fixed size (they don't resize at runtime). Add capacity by
# raising worker_count (more worker tasks), not by resizing a running task.
variable "worker_count" {
  type        = number
  description = "Number of Spark worker tasks (the worker service desired_count)."
  default     = 3
}

variable "master_cpu" {
  type        = number
  description = "Fargate CPU units for the master task (1 vCPU = 1024)."
  default     = 1024
}

variable "master_memory" {
  type        = number
  description = "Fargate memory (MiB) for the master task. Must be a valid pair with master_cpu."
  default     = 2048
}

variable "worker_cpu" {
  type        = number
  description = "Fargate CPU units per worker task (1 vCPU = 1024)."
  default     = 2048
}

variable "worker_memory" {
  type        = number
  description = "Fargate memory (MiB) per worker task. Must be a valid pair with worker_cpu."
  default     = 8192
}

variable "connect_cpu" {
  type        = number
  description = "Fargate CPU units for the Spark Connect task (1 vCPU = 1024)."
  default     = 2048
}

variable "connect_memory" {
  type        = number
  description = "Fargate memory (MiB) for the Spark Connect task. Must be a valid pair with connect_cpu."
  default     = 8192
}

# ----- Spark configuration --------------------------------------------------
variable "enable_connect" {
  type        = bool
  description = "Deploy a Spark Connect server task + public gRPC endpoint (NLB)."
  default     = true
}

variable "extra_spark_conf" {
  type        = map(string)
  description = "Additional spark conf (key => value) appended to spark-defaults on every role. E.g. { \"spark.sql.catalog.unity.uri\" = \"https://uc.example.com\" }."
  default     = {}
}

variable "master_rpc_port" {
  type        = number
  description = "Spark standalone master RPC port (workers connect here, internal only)."
  default     = 7077
}

variable "master_ui_port" {
  type        = number
  description = "Spark master web UI port (behind the ALB)."
  default     = 8080
}

variable "worker_ui_port" {
  type        = number
  description = "Spark worker web UI port (proxied through the master UI)."
  default     = 8081
}

variable "connect_grpc_port" {
  type        = number
  description = "Spark Connect gRPC bind port (behind the NLB)."
  default     = 15002
}

# ----- DNS / TLS (optional) -------------------------------------------------
variable "domain_name" {
  type        = string
  description = "Public FQDN for the master UI over HTTPS (e.g. spark.openlakehousedemos.dev). Empty = HTTP-only on the ALB DNS name. Requires hosted_zone_id."
  default     = ""
}

variable "connect_domain_name" {
  type        = string
  description = "Public FQDN for the Spark Connect gRPC endpoint (e.g. connect.openlakehousedemos.dev). Empty = no Route 53 record (use the NLB DNS name). Requires hosted_zone_id + enable_connect."
  default     = ""
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID that owns the domains (used for ACM DNS validation and alias records)."
  default     = ""
}

variable "cert_domain_name" {
  type        = string
  description = "Domain for the ACM cert. Empty = use domain_name. Set a wildcard like \"*.openlakehousedemos.dev\" to cover both the UI and Connect subdomains with one cert."
  default     = ""
}

# ----- Misc -----------------------------------------------------------------
variable "s3_data_bucket" {
  type        = string
  description = "Optional S3 data-lake bucket name. When set, tasks get read/write access to it via the task IAM role."
  default     = ""
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention for the Spark tasks."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to created resources."
  default     = { project = "open-lakehouse" }
}
