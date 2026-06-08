# Per-presenter hosted JupyterLab + Spark 4.1 on ECS Fargate.
#
# Standalone stack (its own state) — references Scott's existing VPC, subnets,
# ACM wildcard cert and Route53 zone via data sources; does not manage them.
# Each presenter gets: a Fargate task (Jupyter+Spark image + a single-node Kafka
# sidecar for the RTM demo), a target group, an ALB host rule, and a
# nb-<name>.openlakehousedemos.dev DNS record. Tables land in Scott's UC
# (managed_demo); the SDP demo writes catalog-managed Delta there.
#
#   terraform init && terraform apply -var-file=terraform.tfvars
#   terraform destroy   # full teardown after the event

terraform {
  required_version = ">= 1.3"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# ── inputs ──────────────────────────────────────────────────────────────────
variable "aws_region" { default = "us-west-2" }
variable "aws_profile" { default = "open-lakehouse" }
variable "vpc_id" { default = "vpc-0920799a28d2be599" }
variable "domain" { default = "openlakehousedemos.dev" }
variable "image_uri" {
  default = "207734640204.dkr.ecr.us-west-2.amazonaws.com/openlakehouse/notebooks:latest"
}
variable "data_bucket" { default = "uc-quickstart-207734640204-usw2" }
variable "uc_token" {
  type      = string
  sensitive = true # the UC bearer JWT; pass via -var or tfvars (gitignored)
}
variable "presenters" {
  type    = list(string)
  default = ["demo1"] # start with one to validate, then add names and re-apply
}
variable "task_cpu" { default = "2048" } # 2 vCPU
variable "task_memory" { default = "8192" }

# ── lookups ─────────────────────────────────────────────────────────────────
data "aws_caller_identity" "me" {}
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}
data "aws_acm_certificate" "wildcard" {
  domain      = "*.${var.domain}"
  statuses    = ["ISSUED"]
  most_recent = true # 3 identical wildcard certs exist; pick the newest
}
data "aws_route53_zone" "dev" {
  name = "${var.domain}."
}

locals {
  bucket_arn = "arn:aws:s3:::${var.data_bucket}"
}

# ── secret: UC token ────────────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "uc_token" {
  name = "openlakehouse/notebooks/uc-token"
}
resource "aws_secretsmanager_secret_version" "uc_token" {
  secret_id     = aws_secretsmanager_secret.uc_token.id
  secret_string = var.uc_token
}

# ── IAM ─────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exec" {
  name               = "openlakehouse-nb-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}
resource "aws_iam_role_policy_attachment" "exec_managed" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "exec_secret" {
  name = "read-uc-token"
  role = aws_iam_role.exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.uc_token.arn]
    }]
  })
}

# Task role: read the staged raw data + read/write the UC managed storage.
resource "aws_iam_role" "task" {
  name               = "openlakehouse-nb-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}
resource "aws_iam_role_policy" "task_s3" {
  name = "s3-data-and-managed-storage"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [local.bucket_arn, "${local.bucket_arn}/medallion-demo/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [local.bucket_arn, "${local.bucket_arn}/managed_demo/*"]
      },
    ]
  })
}

# ── networking: ALB + task security groups ──────────────────────────────────
resource "aws_security_group" "alb" {
  name   = "openlakehouse-nb-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "task" {
  name   = "openlakehouse-nb-task"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 8889
    to_port         = 8889
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── ALB ─────────────────────────────────────────────────────────────────────
resource "aws_lb" "nb" {
  name               = "openlakehouse-notebooks"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.public.ids
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.nb.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = data.aws_acm_certificate.wildcard.arn
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "open-lakehouse notebooks — use your nb-<name> URL"
      status_code  = "404"
    }
  }
}

resource "aws_ecs_cluster" "nb" {
  name = "openlakehouse-notebooks"
}
resource "aws_cloudwatch_log_group" "nb" {
  name              = "/ecs/openlakehouse-notebooks"
  retention_in_days = 7
}

# ── per-presenter: task def + service + target group + rule + DNS ───────────
resource "aws_ecs_task_definition" "p" {
  for_each                 = toset(var.presenters)
  family                   = "openlakehouse-nb-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "jupyter"
      image     = var.image_uri
      essential = true
      portMappings = [{ containerPort = 8889, protocol = "tcp" }]
      environment = [
        { name = "DEMO_NS", value = "${each.key}_" },
        { name = "JUPYTER_TOKEN", value = each.key },
        { name = "ORDERS_PATH", value = "s3a://${var.data_bucket}/medallion-demo/raw/orders" },
        { name = "DIMS_PATH", value = "s3a://${var.data_bucket}/medallion-demo/raw/dimensions" },
        { name = "MEDALLION_MAX_ROWS", value = "300000" },
      ]
      secrets = [
        { name = "UC_TOKEN", valueFrom = aws_secretsmanager_secret.uc_token.arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.nb.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "jupyter-${each.key}"
        }
      }
    },
    {
      name      = "kafka"
      image     = "apache/kafka:3.9.0"
      essential = false
      environment = [
        { name = "KAFKA_NODE_ID", value = "1" },
        { name = "KAFKA_PROCESS_ROLES", value = "broker,controller" },
        { name = "KAFKA_LISTENERS", value = "PLAINTEXT://:9092,CONTROLLER://:9093" },
        { name = "KAFKA_ADVERTISED_LISTENERS", value = "PLAINTEXT://localhost:9092" },
        { name = "KAFKA_CONTROLLER_QUORUM_VOTERS", value = "1@localhost:9093" },
        { name = "KAFKA_CONTROLLER_LISTENER_NAMES", value = "CONTROLLER" },
        { name = "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP", value = "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT" },
        { name = "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", value = "1" },
        { name = "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", value = "1" },
        { name = "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", value = "1" },
        { name = "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", value = "0" },
        { name = "KAFKA_AUTO_CREATE_TOPICS_ENABLE", value = "true" },
        { name = "CLUSTER_ID", value = "open-lakehouse-rtm-demo01" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.nb.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "kafka-${each.key}"
        }
      }
    },
  ])
}

resource "aws_lb_target_group" "p" {
  for_each    = toset(var.presenters)
  name        = "olh-nb-${each.key}"
  port        = 8889
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/api"
    matcher = "200"
  }
}

resource "aws_lb_listener_rule" "p" {
  for_each     = toset(var.presenters)
  listener_arn = aws_lb_listener.https.arn
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.p[each.key].arn
  }
  condition {
    host_header {
      values = ["nb-${each.key}.${var.domain}"]
    }
  }
}

resource "aws_ecs_service" "p" {
  for_each        = toset(var.presenters)
  name            = "nb-${each.key}"
  cluster         = aws_ecs_cluster.nb.id
  task_definition = aws_ecs_task_definition.p[each.key].arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.public.ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.p[each.key].arn
    container_name   = "jupyter"
    container_port   = 8889
  }
  depends_on = [aws_lb_listener.https]
}

resource "aws_route53_record" "p" {
  for_each = toset(var.presenters)
  zone_id  = data.aws_route53_zone.dev.zone_id
  name     = "nb-${each.key}.${var.domain}"
  type     = "A"
  alias {
    name                   = aws_lb.nb.dns_name
    zone_id                = aws_lb.nb.zone_id
    evaluate_target_health = true
  }
}

# ── outputs ─────────────────────────────────────────────────────────────────
output "presenter_urls" {
  value = { for p in var.presenters : p => "https://nb-${p}.${var.domain}/?token=${p}" }
}
output "alb_dns" { value = aws_lb.nb.dns_name }
