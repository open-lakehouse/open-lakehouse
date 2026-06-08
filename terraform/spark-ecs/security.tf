# ----- ALB security group (public ingress to the master UI) ------------------
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Public ingress to the Spark master UI ALB."
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
# All intra-cluster RPC (master 7077, worker, block-manager, driver/executor
# ephemeral ports) flows between tasks in this SG via the self rule. The ALB
# reaches the master UI; the NLB (no SG of its own) reaches the Connect port
# from within the VPC CIDR.
resource "aws_security_group" "task" {
  name        = "${var.name_prefix}-task"
  description = "Spark Fargate tasks: intra-cluster RPC + LB ingress."
  vpc_id      = local.vpc_id
  tags        = var.tags

  ingress {
    description = "All traffic between Spark tasks (master/worker/executor RPC)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  ingress {
    description     = "Master UI from the ALB"
    from_port       = var.master_ui_port
    to_port         = var.master_ui_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  dynamic "ingress" {
    for_each = local.enable_connect ? [1] : []
    content {
      description = "Spark Connect gRPC from the NLB (VPC CIDR; NLB has no SG)"
      from_port   = var.connect_grpc_port
      to_port     = var.connect_grpc_port
      protocol    = "tcp"
      cidr_blocks = [local.vpc_cidr]
    }
  }

  egress {
    description = "Outbound to ECR, S3, STS, logs, and the open web"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
