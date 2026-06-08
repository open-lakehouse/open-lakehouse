resource "aws_ecs_cluster" "spark" {
  name = "${var.name_prefix}-cluster"
  tags = var.tags

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  # Shared environment for every role. The entrypoint reads SPARK_ROLE (set
  # per task definition) to decide which daemon to launch.
  common_env = [
    { name = "SPARK_MASTER_HOST", value = local.master_fqdn },
    { name = "SPARK_MASTER_PORT", value = tostring(var.master_rpc_port) },
    { name = "SPARK_MASTER_WEBUI_PORT", value = tostring(var.master_ui_port) },
    { name = "SPARK_WORKER_WEBUI_PORT", value = tostring(var.worker_ui_port) },
    { name = "SPARK_CONNECT_PORT", value = tostring(var.connect_grpc_port) },
    { name = "SPARK_REVERSE_PROXY_URL", value = local.master_ui_url },
    { name = "SPARK_EXTRA_CONF", value = local.extra_spark_conf },
    { name = "AWS_REGION", value = var.aws_region },
  ]
}

# ----- Master task -----------------------------------------------------------
resource "aws_ecs_task_definition" "master" {
  family                   = "${var.name_prefix}-master"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.master_cpu)
  memory                   = tostring(var.master_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  tags                     = var.tags

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "spark-master"
      image       = local.image_uri
      essential   = true
      environment = concat(local.common_env, [{ name = "SPARK_ROLE", value = "master" }])
      portMappings = [
        { containerPort = var.master_rpc_port, protocol = "tcp" },
        { containerPort = var.master_ui_port, protocol = "tcp" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.spark.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "master"
        }
      }
    },
  ])
}

# ----- Worker task -----------------------------------------------------------
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_cpu)
  memory                   = tostring(var.worker_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  tags                     = var.tags

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "spark-worker"
      image       = local.image_uri
      essential   = true
      environment = concat(local.common_env, [{ name = "SPARK_ROLE", value = "worker" }])
      portMappings = [
        { containerPort = var.worker_ui_port, protocol = "tcp" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.spark.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    },
  ])
}

# ----- Connect task ----------------------------------------------------------
resource "aws_ecs_task_definition" "connect" {
  count                    = local.enable_connect ? 1 : 0
  family                   = "${var.name_prefix}-connect"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.connect_cpu)
  memory                   = tostring(var.connect_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  tags                     = var.tags

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "spark-connect"
      image       = local.image_uri
      essential   = true
      environment = concat(local.common_env, [{ name = "SPARK_ROLE", value = "connect" }])
      portMappings = [
        { containerPort = var.connect_grpc_port, protocol = "tcp" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.spark.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "connect"
        }
      }
    },
  ])
}

# ----- Master service (1 task, Cloud Map registered, behind the ALB) ---------
resource "aws_ecs_service" "master" {
  name                   = "${var.name_prefix}-master"
  cluster                = aws_ecs_cluster.spark.id
  task_definition        = aws_ecs_task_definition.master.arn
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true
  tags                   = var.tags

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.master.arn
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "spark-master"
    container_port   = var.master_ui_port
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  depends_on = [
    aws_lb_listener.ui_http,
  ]
}

# ----- Worker service (desired_count = worker_count) -------------------------
resource "aws_ecs_service" "worker" {
  name                   = "${var.name_prefix}-worker"
  cluster                = aws_ecs_cluster.spark.id
  task_definition        = aws_ecs_task_definition.worker.arn
  desired_count          = var.worker_count
  launch_type            = "FARGATE"
  enable_execute_command = true
  tags                   = var.tags

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  # Workers dial the master by its Cloud Map name; start them after the master.
  depends_on = [aws_ecs_service.master]
}

# ----- Connect service (1 task, behind the NLB) ------------------------------
resource "aws_ecs_service" "connect" {
  count                  = local.enable_connect ? 1 : 0
  name                   = "${var.name_prefix}-connect"
  cluster                = aws_ecs_cluster.spark.id
  task_definition        = aws_ecs_task_definition.connect[0].arn
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true
  tags                   = var.tags

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.connect[0].arn
    container_name   = "spark-connect"
    container_port   = var.connect_grpc_port
  }

  depends_on = [
    aws_ecs_service.master,
    aws_lb_listener.connect,
  ]
}
