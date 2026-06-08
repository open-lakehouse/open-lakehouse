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

# Resolve the chosen VPC (for its CIDR — used by the task SG to admit NLB traffic).
data "aws_vpc" "selected" {
  id = local.vpc_id
}

data "aws_ecr_repository" "spark" {
  name = var.ecr_repo_name
}

locals {
  vpc_id     = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : tolist(data.aws_subnets.default[0].ids)
  vpc_cidr   = data.aws_vpc.selected.cidr_block
  image_uri  = "${data.aws_ecr_repository.spark.repository_url}:${var.image_tag}"

  # The master's stable, internal Cloud Map FQDN that workers + Connect dial.
  master_fqdn = "master.${var.service_discovery_namespace}"

  enable_https       = var.domain_name != "" && var.hosted_zone_id != ""
  enable_connect     = var.enable_connect
  enable_connect_dns = local.enable_connect && var.connect_domain_name != "" && var.hosted_zone_id != ""

  # Public master URL handed to Spark's UI reverse proxy.
  master_ui_url = local.enable_https ? "https://${var.domain_name}" : "http://${aws_lb.ui.dns_name}"

  # Render extra_spark_conf as the ';'-separated k=v string the entrypoint parses.
  extra_spark_conf = join(";", [for k, v in var.extra_spark_conf : "${k}=${v}"])
}

# ----- Cloud Map: private DNS for internal master/worker discovery -----------
resource "aws_service_discovery_private_dns_namespace" "spark" {
  name        = var.service_discovery_namespace
  description = "Internal discovery for the Spark standalone cluster."
  vpc         = local.vpc_id
  tags        = var.tags
}

resource "aws_service_discovery_service" "master" {
  name = "master"
  tags = var.tags

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.spark.id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 10
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ----- Logs ------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "spark" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
