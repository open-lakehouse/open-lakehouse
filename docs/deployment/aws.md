# Cloud Deployment Guide

This guide covers deploying the lakehouse stack on AWS using managed services. The same patterns apply to other cloud providers (GCP, Azure) with equivalent services.

## Architecture Comparison

| Local Component | AWS Equivalent | Notes |
|-----------------|----------------|-------|
| PostgreSQL 16 | Amazon RDS PostgreSQL | Managed, multi-AZ available |
| SeaweedFS | Amazon S3 | Native S3, no emulation needed |
| Spark 4.x | Amazon EMR | Or EMR Serverless for on-demand |
| Kafka | Amazon MSK | Or MSK Serverless |
| Docker containers | ECS/EKS | Optional for custom workloads |

## AWS Architecture

```
                    ┌─────────────────────────────────────┐
                    │           Amazon VPC                │
                    │                                     │
┌───────────┐       │  ┌─────────────┐  ┌─────────────┐  │
│  Client   │───────┼──│  EMR Cluster │  │  MSK Cluster │  │
└───────────┘       │  │  (Spark 4.x) │  │  (Kafka)     │  │
                    │  └──────┬──────┘  └──────┬──────┘  │
                    │         │                │         │
                    │         ▼                ▼         │
                    │  ┌─────────────────────────────┐   │
                    │  │      Amazon S3 (Data Lake)   │   │
                    │  │  s3://your-bucket/warehouse  │   │
                    │  └─────────────────────────────┘   │
                    │                                     │
                    │  ┌─────────────┐                   │
                    │  │  RDS PostgreSQL │ (Iceberg Catalog)
                    │  └─────────────┘                   │
                    └─────────────────────────────────────┘
```

## Cost Estimates (US regions, on-demand)

| Service | Configuration | Monthly Cost |
|---------|---------------|--------------|
| RDS PostgreSQL | db.t3.micro, 20GB | ~$15 |
| S3 | 100GB storage + requests | ~$3 |
| EMR | 1 master + 2 core (m5.xlarge), 8hr/day | ~$200 |
| MSK | kafka.t3.small, 3 brokers | ~$150 |
| **Development Total** | | **~$370/month** |

**Cost Optimization Tips:**
- Use EMR Serverless for sporadic workloads (pay per use)
- Use Spot instances for EMR workers (60-80% savings)
- Use MSK Serverless for low-throughput streaming
- Schedule EMR clusters to shut down outside work hours

## Setup Instructions

### Prerequisites

```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Configure credentials
aws configure
# Enter: AWS Access Key ID, Secret Access Key, Region (e.g., us-west-2)

# Install Terraform (optional, for IaC)
brew install terraform  # macOS
# or see https://terraform.io/downloads
```

### 1. Create S3 Bucket (Data Lake)

```bash
# Create bucket
aws s3 mb s3://your-lakehouse-bucket --region us-west-2

# Create warehouse directory structure
aws s3api put-object --bucket your-lakehouse-bucket --key warehouse/
```

### 2. Create RDS PostgreSQL (Iceberg Catalog)

```bash
# Create DB subnet group (use your VPC subnets)
aws rds create-db-subnet-group \
  --db-subnet-group-name lakehouse-db-subnet \
  --db-subnet-group-description "Lakehouse DB subnets" \
  --subnet-ids subnet-xxx subnet-yyy

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier lakehouse-catalog \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username lakehouse \
  --master-user-password YourSecurePassword123 \
  --allocated-storage 20 \
  --db-subnet-group-name lakehouse-db-subnet \
  --vpc-security-group-ids sg-xxx \
  --no-publicly-accessible

# Wait for instance to be available
aws rds wait db-instance-available --db-instance-identifier lakehouse-catalog

# Get endpoint
aws rds describe-db-instances \
  --db-instance-identifier lakehouse-catalog \
  --query 'DBInstances[0].Endpoint.Address' --output text
```

Create the Iceberg catalog database:
```bash
# Connect via bastion or VPN
psql -h <rds-endpoint> -U lakehouse -d postgres
CREATE DATABASE iceberg_catalog;
\q
```

### 3. Create EMR Cluster (Spark)

Create a bootstrap script for Iceberg support:
```bash
# Save as s3://your-lakehouse-bucket/scripts/bootstrap.sh
#!/bin/bash
sudo pip3 install pyiceberg
```

```bash
# Upload bootstrap script
aws s3 cp bootstrap.sh s3://your-lakehouse-bucket/scripts/

# Create EMR cluster with Spark 3.5 + Iceberg
# Note: EMR doesn't yet support Spark 4.x, use 3.5 with Iceberg 1.4+
aws emr create-cluster \
  --name "lakehouse-cluster" \
  --release-label emr-7.0.0 \
  --applications Name=Spark Name=Hadoop Name=Livy \
  --instance-type m5.xlarge \
  --instance-count 3 \
  --use-default-roles \
  --ec2-attributes SubnetId=subnet-xxx,KeyName=your-key \
  --bootstrap-actions Path=s3://your-lakehouse-bucket/scripts/bootstrap.sh \
  --configurations '[
    {
      "Classification": "spark-defaults",
      "Properties": {
        "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.iceberg.catalog-impl": "org.apache.iceberg.rest.RESTCatalog",
        "spark.sql.catalog.iceberg.uri": "https://<unity-catalog-host>/api/2.1/unity-catalog/iceberg",
        "spark.sql.catalog.iceberg.warehouse": "unity",
        "spark.sql.catalog.iceberg.token": "<oauth-token-or-not_used>"
      }
    }
  ]'
```

### 4. Create MSK Cluster (Kafka) - Optional

```bash
# Create MSK configuration
aws kafka create-configuration \
  --name "lakehouse-kafka-config" \
  --kafka-versions "3.6.0" \
  --server-properties file://kafka-config.properties

# Create MSK cluster
aws kafka create-cluster \
  --cluster-name "lakehouse-kafka" \
  --broker-node-group-info file://broker-config.json \
  --kafka-version "3.6.0" \
  --number-of-broker-nodes 3 \
  --encryption-info file://encryption-config.json
```

For simpler setups, consider **MSK Serverless**:
```bash
aws kafka create-cluster-v2 \
  --cluster-name "lakehouse-kafka-serverless" \
  --serverless '{
    "vpcConfigs": [{
      "subnetIds": ["subnet-xxx", "subnet-yyy"],
      "securityGroupIds": ["sg-xxx"]
    }],
    "clientAuthentication": {
      "sasl": { "iam": { "enabled": true } }
    }
  }'
```

## Configuration Files

### spark-defaults.conf (for AWS)

```properties
# Iceberg via Unity Catalog OSS REST (the only catalog mode in this repo)
spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl=org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri=https://<unity-catalog-host>/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse=unity
spark.sql.catalog.iceberg.token=<oauth-token-or-not_used>

# S3 Configuration
spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem
spark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain

# Performance tuning
spark.sql.adaptive.enabled=true
spark.sql.adaptive.coalescePartitions.enabled=true
```

### .env (for AWS)

```bash
# PostgreSQL (RDS)
POSTGRES_USER=lakehouse
POSTGRES_PASSWORD=YourSecurePassword123
POSTGRES_HOST=<rds-endpoint>.rds.amazonaws.com
POSTGRES_PORT=5432

# S3 (native AWS)
S3_ENDPOINT=https://s3.us-west-2.amazonaws.com
S3_ACCESS_KEY=  # Leave empty, use IAM roles
S3_SECRET_KEY=  # Leave empty, use IAM roles
S3_BUCKET=your-lakehouse-bucket
S3_WAREHOUSE=s3://your-lakehouse-bucket/warehouse

# Iceberg
ICEBERG_CATALOG_URI=jdbc:postgresql://${POSTGRES_HOST}:5432/iceberg_catalog
ICEBERG_WAREHOUSE=${S3_WAREHOUSE}

# Kafka (MSK)
KAFKA_BOOTSTRAP_SERVERS=<msk-bootstrap-servers>:9092
```

## EMR Serverless (Recommended for Development)

EMR Serverless is more cost-effective for sporadic workloads:

```bash
# Create EMR Serverless application
aws emr-serverless create-application \
  --name lakehouse-spark \
  --release-label emr-7.0.0 \
  --type SPARK \
  --initial-capacity '{
    "DRIVER": {
      "workerCount": 1,
      "workerConfiguration": {
        "cpu": "2vCPU",
        "memory": "4GB"
      }
    },
    "EXECUTOR": {
      "workerCount": 2,
      "workerConfiguration": {
        "cpu": "2vCPU",
        "memory": "4GB"
      }
    }
  }'

# Submit a job
aws emr-serverless start-job-run \
  --application-id <app-id> \
  --execution-role-arn arn:aws:iam::xxx:role/EMRServerlessRole \
  --job-driver '{
    "sparkSubmit": {
      "entryPoint": "s3://your-lakehouse-bucket/scripts/my-job.py",
      "sparkSubmitParameters": "--conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog"
    }
  }'
```

## IAM Roles and Policies

### EMR Service Role Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-lakehouse-bucket",
        "arn:aws:s3:::your-lakehouse-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "rds-db:connect"
      ],
      "Resource": [
        "arn:aws:rds-db:us-west-2:*:dbuser:*/lakehouse"
      ]
    }
  ]
}
```

## Networking Considerations

### VPC Setup

1. **Private Subnets**: Run EMR, RDS, and MSK in private subnets
2. **NAT Gateway**: Required for EMR nodes to download packages
3. **VPC Endpoints**: Create endpoints for S3 to avoid NAT costs
4. **Security Groups**:
   - EMR → RDS: Allow port 5432
   - EMR → MSK: Allow port 9092
   - EMR → S3: Via VPC endpoint

```bash
# Create S3 VPC endpoint (saves NAT costs)
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-xxx \
  --service-name com.amazonaws.us-west-2.s3 \
  --route-table-ids rtb-xxx
```

## Migrating from Local to AWS

1. **Export local Iceberg tables** (if needed):
   ```bash
   # Snapshot local tables
   spark-submit scripts/export-tables.py --output s3://your-bucket/migration/
   ```

2. **Update configuration**:
   - Change `.env` to use RDS endpoint
   - Change S3 endpoint to AWS S3
   - Update spark-defaults.conf

3. **Test connectivity**:
   ```bash
   # From EMR master node
   psql -h <rds-endpoint> -U lakehouse -d iceberg_catalog -c "SELECT 1;"
   aws s3 ls s3://your-lakehouse-bucket/warehouse/
   ```

## Monitoring

### CloudWatch Dashboards

Key metrics to monitor:
- EMR: `AppsRunning`, `CoreNodesRunning`, `HDFSUtilization`
- RDS: `CPUUtilization`, `FreeStorageSpace`, `DatabaseConnections`
- MSK: `KafkaDataLogsDiskUsed`, `UnderReplicatedPartitions`
- S3: `BucketSizeBytes`, `NumberOfObjects`

### Logging

```bash
# EMR logs → S3
aws emr create-cluster ... --log-uri s3://your-bucket/emr-logs/

# Enable RDS enhanced monitoring
aws rds modify-db-instance \
  --db-instance-identifier lakehouse-catalog \
  --monitoring-interval 60 \
  --monitoring-role-arn arn:aws:iam::xxx:role/rds-monitoring-role
```

## Cleanup

```bash
# Terminate EMR cluster
aws emr terminate-clusters --cluster-ids j-XXXXX

# Delete RDS instance (careful!)
aws rds delete-db-instance \
  --db-instance-identifier lakehouse-catalog \
  --skip-final-snapshot

# Delete MSK cluster
aws kafka delete-cluster --cluster-arn arn:aws:kafka:...

# Empty and delete S3 bucket
aws s3 rm s3://your-lakehouse-bucket --recursive
aws s3 rb s3://your-lakehouse-bucket
```

## Next Steps

1. See `terraform/` directory for Infrastructure as Code templates
2. Deploy a managed Unity Catalog OSS instance behind a load balancer if you need multi-engine access from outside the VPC
3. For production, implement proper CI/CD with CodePipeline or GitHub Actions
