# open-lakehouse task runner.
#
# Install `just`: https://github.com/casey/just (see README "Deploying to AWS").
# List recipes:  `just` or `just --list`.

# Default release tag for image builds / deploys. Prefers RELEASE_TAG, falling
# back to the legacy SPARK_IMAGE_TAG, then a hardcoded default.
release_tag := env_var_or_default("RELEASE_TAG", env_var_or_default("SPARK_IMAGE_TAG", "v0.1.0"))

# Show available recipes.
default:
    @just --list

# Deploy a stack to AWS. Usage: `just deploy spark-ecs [tag]` or `just deploy mlflow-ecs [tag]`.
deploy target tag=release_tag:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ target }}" in
      spark-ecs)
        bash scripts/terraform/deploy-spark-ecs.sh "{{ tag }}"
        ;;
      mlflow-ecs)
        bash scripts/terraform/deploy-mlflow-ecs.sh "{{ tag }}"
        ;;
      *)
        echo "ERROR: unknown deploy target '{{ target }}'." >&2
        echo "Known targets: spark-ecs, mlflow-ecs" >&2
        exit 1
        ;;
    esac

# Build + push the Spark image to ECR. Usage: `just spark-ecs-push [tag]`.
spark-ecs-push tag=release_tag:
    bash scripts/terraform/spark-ecr-push.sh "{{ tag }}"

# Tear down the spark-ecs deployment (ALB, NLB, services, roles, Cloud Map).
spark-ecs-destroy:
    terraform -chdir=terraform/spark-ecs destroy

# Print the spark-ecs Terraform outputs (URLs, service names).
spark-ecs-outputs:
    terraform -chdir=terraform/spark-ecs output

# Build + push the MLflow image to ECR. Usage: `just mlflow-ecs-push [tag]`.
mlflow-ecs-push tag=release_tag:
    bash scripts/terraform/mlflow-ecr-push.sh "{{ tag }}"

# Tear down the mlflow-ecs deployment (ALB, service, roles, log group).
mlflow-ecs-destroy:
    terraform -chdir=terraform/mlflow-ecs destroy

# Print the mlflow-ecs Terraform outputs (URL, service name).
mlflow-ecs-outputs:
    terraform -chdir=terraform/mlflow-ecs output
