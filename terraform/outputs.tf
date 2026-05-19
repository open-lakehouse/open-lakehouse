# Lakehouse Stack - Terraform Outputs

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.lakehouse.id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "s3_bucket_name" {
  description = "Name of the S3 data lake bucket"
  value       = aws_s3_bucket.lakehouse.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 data lake bucket"
  value       = aws_s3_bucket.lakehouse.arn
}

output "s3_warehouse_path" {
  description = "S3 path for Iceberg warehouse"
  value       = "s3://${aws_s3_bucket.lakehouse.id}/warehouse"
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.catalog.endpoint
}

output "rds_address" {
  description = "RDS PostgreSQL address (without port)"
  value       = aws_db_instance.catalog.address
}

output "iceberg_catalog_uri" {
  description = "JDBC URI for Iceberg catalog"
  value       = "jdbc:postgresql://${aws_db_instance.catalog.endpoint}/iceberg_catalog"
  sensitive   = true
}

output "emr_cluster_id" {
  description = "ID of the EMR cluster (if created)"
  value       = var.create_emr_cluster ? aws_emr_cluster.lakehouse[0].id : null
}

output "emr_master_dns" {
  description = "DNS name of EMR master node (if created)"
  value       = var.create_emr_cluster ? aws_emr_cluster.lakehouse[0].master_public_dns : null
}

# Generate .env file content
output "env_file_content" {
  description = "Content for .env file (copy to your local .env)"
  sensitive   = true
  value       = <<-EOT
    # PostgreSQL (RDS)
    POSTGRES_USER=${var.db_username}
    POSTGRES_PASSWORD=${var.db_password}
    POSTGRES_HOST=${aws_db_instance.catalog.address}
    POSTGRES_PORT=5432

    # S3 (AWS native - credentials via IAM)
    S3_ENDPOINT=https://s3.${var.aws_region}.amazonaws.com
    S3_BUCKET=${aws_s3_bucket.lakehouse.id}
    S3_WAREHOUSE=s3://${aws_s3_bucket.lakehouse.id}/warehouse

    # Iceberg
    ICEBERG_CATALOG_URI=jdbc:postgresql://${aws_db_instance.catalog.endpoint}/iceberg_catalog
    ICEBERG_WAREHOUSE=s3://${aws_s3_bucket.lakehouse.id}/warehouse
  EOT
}
