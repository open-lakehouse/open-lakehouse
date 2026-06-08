output "master_ui_url" {
  value       = local.master_ui_url
  description = "Public URL for the Spark master web UI (worker UIs are proxied at /proxy/<worker-id>)."
}

output "connect_url" {
  value = local.enable_connect ? (
    local.enable_connect_dns ? "sc://${var.connect_domain_name}:443" : "sc://${aws_lb.connect[0].dns_name}:${var.connect_grpc_port}"
  ) : null
  description = "Spark Connect client URL. With a domain it is TLS on :443 (use SSL); otherwise raw TCP on the gRPC port."
}

output "alb_dns_name" {
  value       = aws_lb.ui.dns_name
  description = "DNS name of the master UI ALB."
}

output "nlb_dns_name" {
  value       = local.enable_connect ? aws_lb.connect[0].dns_name : null
  description = "DNS name of the Spark Connect NLB (null when Connect is disabled)."
}

output "master_internal_host" {
  value       = local.master_fqdn
  description = "Cloud Map FQDN the master advertises to workers and the Connect server."
}

output "cluster_name" {
  value       = aws_ecs_cluster.spark.name
  description = "ECS cluster name (used for ECS Exec into tasks)."
}

output "master_service_name" {
  value       = aws_ecs_service.master.name
  description = "ECS service name for the Spark master."
}

output "worker_service_name" {
  value       = aws_ecs_service.worker.name
  description = "ECS service name for the Spark workers (scale via worker_count)."
}

output "connect_service_name" {
  value       = local.enable_connect ? aws_ecs_service.connect[0].name : null
  description = "ECS service name for the Spark Connect server (null when disabled)."
}

output "log_group" {
  value       = aws_cloudwatch_log_group.spark.name
  description = "CloudWatch Logs group for the Spark tasks."
}

output "ecr_repository_url" {
  value       = data.aws_ecr_repository.spark.repository_url
  description = "ECR repository URL the image is pulled from."
}
