# `spark-ecs` — Spark 4.1 standalone cluster on ECS Fargate

A self-contained Terraform recipe that deploys an Apache Spark 4.1 **standalone**
cluster on AWS ECS Fargate:

- **1 master** task (RPC + web UI)
- **N worker** tasks (`worker_count`, default 3)
- **1 Spark Connect** server task (optional, `enable_connect`)

Internal master/worker discovery uses **AWS Cloud Map** private DNS; public
access uses **Route 53 + ALB** (master UI) and **Route 53 + NLB** (Spark Connect
gRPC), all under your hosted zone (e.g. `openlakehousedemos.dev`).

```
Browser  ── spark.openlakehousedemos.dev   ─▶ ALB :443 ─▶ master UI :8080
Client   ── connect.openlakehousedemos.dev ─▶ NLB :443 ─▶ connect  :15002
                                              (internal)  master.spark.local:7077
                                                          ▲          ▲
                                              workers ────┘   connect ┘
```

## Why these choices

- **Cloud Map for the cluster, not the ALB.** Worker→master registration is
  Spark's own RPC (port 7077), not HTTP — an ALB cannot carry it. The master is
  published at a stable internal name (`master.spark.local`) that workers and the
  Connect server dial. Each Fargate task has a unique ENI IP, so the container
  entrypoint reads the task's IP from the ECS metadata endpoint and exports it as
  `SPARK_LOCAL_IP` (without this, master↔worker RPC silently fails).
- **One public host for the UI, no per-worker subdomains.** The master runs with
  `spark.ui.reverseProxy=true`, so every worker UI is browsable *through* the
  master at `/proxy/<worker-id>`. Worker tasks are ephemeral and their count is
  dynamic, so static per-worker DNS would be brittle and add no value.
- **Connect over an NLB, not the ALB.** An NLB (L4) passes HTTP/2 cleanly. With a
  domain configured it terminates TLS on `:443` (ALPN `h2`) and forwards plaintext
  h2c to the Connect server, so clients connect at `sc://connect.<zone>:443` with
  SSL.

## Prerequisites

- AWS credentials with permission to manage ECS, ECR, EC2/VPC, ELB, Route 53,
  ACM, IAM, Cloud Map, and CloudWatch Logs.
- `aws`, `docker` (with buildx), and `terraform` (>= 1.5) on PATH.
- `just` (the command runner) for the one-liner deploy — see install below.
- A Route 53 hosted zone for your domain (for HTTPS). Set `hosted_zone_id`.

### Installing `just`

[`just`](https://github.com/casey/just) is a small command runner used by the
repo's `Justfile`.

```bash
# macOS
brew install just

# Linux (Debian/Ubuntu)
sudo apt install just            # or: cargo install just

# Any platform with a Rust toolchain
cargo install just

# Prebuilt binary (no package manager)
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
```

Verify with `just --version`, then list recipes with `just` (or `just --list`).

## Configuration

There are two ways to supply values (you can mix them; precedence is
`variables.tf` defaults < `terraform.tfvars` < `.env-terraform.spark-ecs` < CLI tag):

1. Env file (recommended for the common DNS/image knobs). Copy the template and
   fill it in — it is gitignored, so your real values never get committed:

   ```bash
   cp .env-terraform.spark-ecs.example .env-terraform.spark-ecs
   # edit SPARK_CLUSTER_DOMAIN_NAME, SPARK_CLUSTER_HOSTED_ZONE_ID, etc.
   ```

   | Env var | Maps to (TF var) |
   |---------|------------------|
   | `SPARK_CONTAINER_RELEASE_TAG` | `image_tag` (and the build/push tag) |
   | `SPARK_CLUSTER_DOMAIN_NAME` | `domain_name` |
   | `SPARK_CLUSTER_CONNECT_DOMAIN_NAME` | `connect_domain_name` |
   | `SPARK_CLUSTER_HOSTED_ZONE_ID` | `hosted_zone_id` |
   | `SPARK_CLUSTER_CERT_DOMAIN_NAME` | `cert_domain_name` |
   | `SPARK_ECR_REPO` | `ecr_repo_name` |
   | `AWS_REGION` | `aws_region` |

   `scripts/terraform/deploy-spark-ecs.sh` and `scripts/terraform/spark-ecr-push.sh`
   source this file and export the mapped `TF_VAR_*` values automatically.

2. `terraform.tfvars` for everything else (sizing, `worker_count`,
   `extra_spark_conf`, `s3_data_bucket`, …):

   ```bash
   cp terraform/spark-ecs/terraform.tfvars.example terraform/spark-ecs/terraform.tfvars
   ```

## Deploy

The simplest path, from the repo root:

```bash
# Build the image, apply Terraform, wait, and print the endpoints.
just deploy spark-ecs            # or: just deploy spark-ecs v0.2.0
```

Related recipes:

```bash
just spark-ecs-push [tag]        # build + push the image only
just spark-ecs-outputs           # print URLs / service names
just spark-ecs-destroy           # tear the stack down
```

Prefer raw scripts/Terraform? The equivalents are:

```bash
scripts/terraform/spark-ecr-push.sh v0.1.0
terraform -chdir=terraform/spark-ecs init
terraform -chdir=terraform/spark-ecs apply
# or the one-shot wrapper:
scripts/terraform/deploy-spark-ecs.sh v0.1.0
```

Outputs include `master_ui_url`, `connect_url`, `cluster_name`, and the service
names.

## Connecting

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .remote("sc://connect.openlakehousedemos.dev:443/;use_ssl=true")
    .getOrCreate()
)
```

Browse the cluster at `https://spark.openlakehousedemos.dev`.

## Configuration knobs

| Variable | Purpose | Default |
|----------|---------|---------|
| `worker_count` | Number of worker tasks (scale here, not task size) | `3` |
| `master_cpu` / `master_memory` | Master task size | `1024` / `2048` |
| `worker_cpu` / `worker_memory` | Per-worker task size | `2048` / `8192` |
| `connect_cpu` / `connect_memory` | Connect task size | `2048` / `8192` |
| `enable_connect` | Deploy the Connect server + NLB | `true` |
| `extra_spark_conf` | `map(string)` appended to spark-defaults on every role | `{}` |
| `domain_name` / `connect_domain_name` / `hosted_zone_id` / `cert_domain_name` | Public DNS + TLS | empty (HTTP-only) |
| `s3_data_bucket` | Grant tasks R/W on a data-lake bucket | empty |

`extra_spark_conf` is the supported way to add Spark settings (e.g. wire a remote
Unity Catalog, set a warehouse dir, override the S3 endpoint) without rebuilding
the image — entries are appended to `spark-defaults.conf` at container start.

## Image

The image (`terraform/spark-ecs/docker/`) is a thin layer over
`apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu` that bakes in the
lakehouse JARs (Delta 4.2.0, Iceberg 1.10.0, Unity Catalog connector 0.3.0,
Hadoop-AWS 3.4.1, AWS SDK v2 2.24.6, Spark Connect 4.1.0) plus the entrypoint
that selects the role via `SPARK_ROLE`.

## Cost & teardown

This stack runs an ALB, an NLB, and several always-on Fargate tasks — it is not
free. Tear it down with:

```bash
terraform -chdir=terraform/spark-ecs destroy
```

## Notes / limitations

- Fargate tasks are fixed-size; "more capacity" means more workers
  (`worker_count`), not a bigger task.
- The cluster has no shared filesystem — event logs are per-task local. Point
  Spark at S3 (via `extra_spark_conf` + `s3_data_bucket`) for durable storage.
- Connect's gRPC port is admitted from the VPC CIDR (default NLB forwarding).
  Public reachability is via the NLB.
