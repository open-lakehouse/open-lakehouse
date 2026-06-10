# ----- ALB security group (public ingress to the tracking server) -----------
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Public ingress to the MLflow tracking server ALB."
  vpc_id      = local.vpc_id
  tags        = var.tags

  ingress {
    description = "HTTP from the open web"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = local.enable_https ? [1] : []
    content {
      description = "HTTPS from the open web"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ----- Task security group ---------------------------------------------------
# Only the ALB may reach the tracking port. Egress is open so the task can reach
# the external Postgres, S3, ECR, Secrets Manager, and CloudWatch Logs.
resource "aws_security_group" "task" {
  name        = "${var.name_prefix}-task"
  description = "MLflow Fargate task: tracking port from the ALB, open egress."
  vpc_id      = local.vpc_id
  tags        = var.tags

  ingress {
    description     = "Tracking server port from the ALB"
    from_port       = var.mlflow_port
    to_port         = var.mlflow_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound to Postgres, S3, ECR, Secrets Manager, logs, and the open web"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
