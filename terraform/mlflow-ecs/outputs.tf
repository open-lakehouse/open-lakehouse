output "mlflow_url" {
  value       = local.mlflow_url
  description = "Public URL for the MLflow tracking server UI / API. Set MLFLOW_TRACKING_URI to this."
}

output "alb_dns_name" {
  value       = aws_lb.ui.dns_name
  description = "DNS name of the tracking server ALB."
}

output "cluster_name" {
  value       = aws_ecs_cluster.mlflow.name
  description = "ECS cluster name (used for ECS Exec into the task)."
}

output "service_name" {
  value       = aws_ecs_service.mlflow.name
  description = "ECS service name for the MLflow tracking server."
}

output "log_group" {
  value       = aws_cloudwatch_log_group.mlflow.name
  description = "CloudWatch Logs group for the MLflow task."
}

output "ecr_repository_url" {
  value       = data.aws_ecr_repository.mlflow.repository_url
  description = "ECR repository URL the image is pulled from."
}

output "artifacts_destination" {
  value       = local.artifacts_destination
  description = "S3 URI the tracking server proxies artifacts to/from."
}
