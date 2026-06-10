# ----- IAM: task execution role (pull image, write logs, read DB secret) -----
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow the agent to resolve the DB password secret it injects into the task.
# Supports both Secrets Manager ARNs and SSM parameter ARNs.
data "aws_iam_policy_document" "execution_secret" {
  dynamic "statement" {
    for_each = can(regex(":secretsmanager:", var.pg_password_secret_arn)) ? [1] : []
    content {
      sid       = "ReadDbPasswordSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.pg_password_secret_arn]
    }
  }

  dynamic "statement" {
    for_each = can(regex(":ssm:", var.pg_password_secret_arn)) ? [1] : []
    content {
      sid       = "ReadDbPasswordParameter"
      effect    = "Allow"
      actions   = ["ssm:GetParameters"]
      resources = [var.pg_password_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "read-db-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secret.json
}

# ----- IAM: task role (ECS Exec for debugging + S3 artifact access) ----------
resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "task" {
  statement {
    sid    = "SSMExec"
    effect = "Allow"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }

  # The tracking server proxies artifact I/O, so the task role needs read/write
  # on the artifact prefix and list on the bucket.
  statement {
    sid       = "ListArtifactBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.artifact_bucket}"]
  }

  statement {
    sid       = "ArtifactObjectRW"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.artifact_bucket}/${var.artifact_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "mlflow-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}
