resource "aws_ecs_cluster" "mlflow" {
  name = "${var.name_prefix}-cluster"
  tags = var.tags

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ----- Task definition -------------------------------------------------------
# Single container running the open-lakehouse MLflow image. The entrypoint:
#   - connects to the existing Postgres backend (psycopg2 ships in the -full base)
#   - serves artifacts by proxying to S3 (--artifacts-destination), so remote
#     clients need no bucket credentials; the task role grants S3 access
#   - appends --allowed-hosts / --cors-allowed-origins via MLFLOW_EXTRA_ARGS so
#     the uvicorn security middleware accepts requests through the ALB
resource "aws_ecs_task_definition" "mlflow" {
  family                   = "${var.name_prefix}-server"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  tags                     = var.tags

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "mlflow"
      image     = local.image_uri
      essential = true
      environment = [
        { name = "POSTGRES_HOST", value = var.pg_host },
        { name = "POSTGRES_PORT", value = tostring(var.pg_port) },
        { name = "MLFLOW_PG_USER", value = var.pg_user },
        { name = "MLFLOW_PG_DB", value = var.pg_database },
        { name = "MLFLOW_PG_SSLMODE", value = var.pg_sslmode },
        { name = "MLFLOW_SKIP_PROVISION", value = var.skip_provision ? "1" : "0" },
        # Provisioning path (skip_provision=false): the MLflow role acts as its
        # own admin, connecting to pg_admin_db to CREATE DATABASE. Ignored when
        # skip_provision=true.
        { name = "POSTGRES_USER", value = var.pg_user },
        { name = "POSTGRES_ADMIN_DB", value = var.pg_admin_db },
        # Proxy artifacts to S3 instead of handing clients a raw s3:// root.
        { name = "MLFLOW_ARTIFACT_ROOT_FLAG", value = "--artifacts-destination" },
        { name = "MLFLOW_ARTIFACTS_DESTINATION", value = local.artifacts_destination },
        { name = "MLFLOW_EXTRA_ARGS", value = local.mlflow_extra_args },
        { name = "AWS_REGION", value = var.aws_region },
      ]
      # DB password injected by the agent from Secrets Manager / SSM, never baked
      # in. POSTGRES_PASSWORD mirrors it for the provisioning path (same role).
      secrets = [
        { name = "MLFLOW_PG_PASS", valueFrom = var.pg_password_secret_arn },
        { name = "POSTGRES_PASSWORD", valueFrom = var.pg_password_secret_arn },
      ]
      portMappings = [
        { containerPort = var.mlflow_port, protocol = "tcp" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.mlflow.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "mlflow"
        }
      }
    },
  ])
}

# ----- Service (behind the ALB) ----------------------------------------------
resource "aws_ecs_service" "mlflow" {
  name                   = "${var.name_prefix}-server"
  cluster                = aws_ecs_cluster.mlflow.id
  task_definition        = aws_ecs_task_definition.mlflow.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true
  tags                   = var.tags

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "mlflow"
    container_port   = var.mlflow_port
  }

  # Give a new task time to run DB migrations and pass health checks before the
  # ALB starts counting it unhealthy.
  health_check_grace_period_seconds = 120

  depends_on = [
    aws_lb_listener.ui_http,
  ]
}
