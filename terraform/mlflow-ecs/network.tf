data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ----- Networking: default VPC + its public subnets unless overridden --------
data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = length(var.subnet_ids) == 0 ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

data "aws_ecr_repository" "mlflow" {
  name = var.ecr_repo_name
}

locals {
  vpc_id     = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : tolist(data.aws_subnets.default[0].ids)
  image_uri  = "${data.aws_ecr_repository.mlflow.repository_url}:${var.image_tag}"

  enable_https = var.domain_name != "" && var.hosted_zone_id != ""

  # Public URL clients and browsers use to reach the tracking server.
  mlflow_url = local.enable_https ? "https://${var.domain_name}" : "http://${aws_lb.ui.dns_name}"

  # Proxied artifact root: the server streams artifacts to/from S3 so remote
  # clients never need bucket credentials (the task role grants S3 access).
  artifacts_destination = "s3://${var.artifact_bucket}/${var.artifact_prefix}"

  # Host allow-list (DNS-rebinding protection). Default to the public FQDN when
  # HTTPS is on; otherwise accept any host on the raw ALB DNS name.
  allowed_hosts = var.allowed_hosts != "" ? var.allowed_hosts : (
    local.enable_https ? var.domain_name : "*"
  )

  # CORS origins. Default to the public https origin when a domain is set.
  cors_allowed_origins = var.cors_allowed_origins != "" ? var.cors_allowed_origins : (
    local.enable_https ? "https://${var.domain_name}" : ""
  )

  # Flags appended to `mlflow server` by the image entrypoint (MLFLOW_EXTRA_ARGS).
  mlflow_extra_args = trimspace(join(" ", concat(
    ["--allowed-hosts", local.allowed_hosts],
    local.cors_allowed_origins != "" ? ["--cors-allowed-origins", local.cors_allowed_origins] : [],
  )))
}

# ----- Logs ------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "mlflow" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
