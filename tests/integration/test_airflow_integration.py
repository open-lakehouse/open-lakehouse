"""Integration tests for Airflow orchestration.

Tests Airflow setup, DAG validation, and configuration without requiring
running containers. For live Airflow testing, the container must be started.
"""

import os
import subprocess
import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAGS_DIR = os.path.join(PROJECT_ROOT, "dags")


@pytest.mark.integration
class TestAirflowDockerConfiguration:
    """Test Airflow Docker configuration is valid."""

    def test_docker_compose_airflow_syntax(self, project_root):
        """Validate docker-compose-airflow.yml syntax."""
        compose_path = os.path.join(project_root, "docker-compose-airflow.yml")
        if not os.path.exists(compose_path):
            pytest.skip("docker-compose-airflow.yml not present")

        # Create minimal .env for validation
        env = {
            **os.environ,
            "COMPOSE_PROJECT_NAME": "test",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "S3_ACCESS_KEY": "test",
            "S3_SECRET_KEY": "test",
            "S3_ENDPOINT": "http://localhost:8333",
            "AIRFLOW_FERNET_KEY": "test-fernet-key-for-ci",
        }

        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose-airflow.yml", "config", "--quiet"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env,
        )
        # Allow for missing .env file but syntax should be valid
        assert result.returncode == 0 or "env file" in result.stderr.lower(), \
            f"Docker compose validation failed: {result.stderr}"

    def test_dockerfile_exists(self, project_root):
        """Verify Airflow Dockerfile exists."""
        dockerfile = os.path.join(project_root, "docker", "airflow", "Dockerfile")
        assert os.path.exists(dockerfile), "docker/airflow/Dockerfile not found"

    def test_dockerfile_uses_spark_41(self, project_root):
        """Dockerfile should use Spark 4.1 as default."""
        dockerfile = os.path.join(project_root, "docker", "airflow", "Dockerfile")
        with open(dockerfile) as f:
            content = f.read()

        assert "SPARK_VERSION=4.1" in content, "Dockerfile should use Spark 4.1"

    def test_docker_compose_network_mode(self, project_root):
        """Docker compose should use host network mode."""
        compose_path = os.path.join(project_root, "docker-compose-airflow.yml")
        with open(compose_path) as f:
            config = yaml.safe_load(f)

        # Check x-airflow-common for network_mode
        common = config.get("x-airflow-common", {})
        assert common.get("network_mode") == "host", \
            "Airflow should use host network mode for service access"


@pytest.mark.integration
class TestAirflowDAGValidation:
    """Test DAG files are valid and complete."""

    def test_all_dags_have_valid_python_syntax(self, project_root):
        """All DAG files should compile without errors."""
        dags_dir = os.path.join(project_root, "dags")
        if not os.path.exists(dags_dir):
            pytest.skip("dags/ directory not present")

        dag_files = [f for f in os.listdir(dags_dir) if f.endswith(".py")]
        assert len(dag_files) > 0, "No DAG files found"

        for dag_file in dag_files:
            dag_path = os.path.join(dags_dir, dag_file)
            result = subprocess.run(
                ["python3", "-m", "py_compile", dag_path],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error in {dag_file}: {result.stderr}"

    def test_medallion_pipeline_references_correct_scripts(self, project_root):
        """Medallion pipeline DAG should reference correct script paths."""
        dag_path = os.path.join(project_root, "dags", "lakehouse_medallion_pipeline.py")
        with open(dag_path) as f:
            content = f.read()

        # Should reference pipelines directory
        assert "/scripts/pipelines/" in content, \
            "DAG should reference scripts/pipelines/ directory"

    def test_dags_use_spark_version_variable(self, project_root):
        """DAGs should support configurable Spark version."""
        dags_dir = os.path.join(project_root, "dags")
        dag_files = [f for f in os.listdir(dags_dir) if f.endswith(".py")]

        for dag_file in dag_files:
            dag_path = os.path.join(dags_dir, dag_file)
            with open(dag_path) as f:
                content = f.read()

            assert "Variable.get" in content, \
                f"{dag_file} should use Airflow Variables for configuration"


@pytest.mark.integration
class TestAirflowCLIIntegration:
    """Test lakehouse CLI has Airflow support."""

    def test_cli_start_airflow_command(self, project_root, lakehouse_cli):
        """CLI should have start airflow command."""
        result = subprocess.run(
            [lakehouse_cli, "help"],
            capture_output=True,
            text=True,
        )
        assert "airflow" in result.stdout.lower(), "CLI help should mention airflow"

    def test_cli_references_airflow_compose(self, project_root, lakehouse_cli):
        """CLI should reference docker-compose-airflow.yml."""
        with open(lakehouse_cli) as f:
            content = f.read()

        assert "docker-compose-airflow.yml" in content, \
            "CLI should reference docker-compose-airflow.yml"

    def test_cli_has_airflow_log_commands(self, project_root, lakehouse_cli):
        """CLI should support airflow log viewing."""
        with open(lakehouse_cli) as f:
            content = f.read()

        # Should have log commands for airflow services
        assert "airflow-webserver" in content
        assert "airflow-scheduler" in content


@pytest.mark.integration
class TestAirflowConfigurationFiles:
    """Test Airflow configuration files."""

    def test_setup_connections_script_is_executable(self, project_root):
        """Connection setup script should be executable or have shebang."""
        script_path = os.path.join(project_root, "config", "airflow", "setup_connections.sh")
        if not os.path.exists(script_path):
            pytest.skip("setup_connections.sh not present")

        with open(script_path) as f:
            first_line = f.readline()

        assert first_line.startswith("#!/bin/bash") or first_line.startswith("#!/usr/bin/env bash"), \
            "Script should have bash shebang"

    def test_setup_connections_configures_all_services(self, project_root):
        """Setup script should configure all required connections."""
        script_path = os.path.join(project_root, "config", "airflow", "setup_connections.sh")
        with open(script_path) as f:
            content = f.read()

        required_connections = ["kafka", "spark_local", "postgres", "unity_catalog", "mlflow"]
        for conn in required_connections:
            assert conn in content.lower(), f"Missing connection setup for: {conn}"

    def test_env_example_has_fernet_key(self, project_root):
        """env.example should document AIRFLOW_FERNET_KEY."""
        env_path = os.path.join(project_root, ".env.example")
        with open(env_path) as f:
            content = f.read()

        assert "AIRFLOW_FERNET_KEY" in content, \
            "AIRFLOW_FERNET_KEY should be documented in .env.example"


@pytest.mark.integration
class TestAirflowDocumentation:
    """Test Airflow documentation is complete."""

    def test_airflow_guide_exists(self, project_root):
        """Airflow guide should exist."""
        guide_path = os.path.join(project_root, "docs", "guides", "airflow.md")
        assert os.path.exists(guide_path), "docs/guides/airflow.md not found"

    def test_airflow_guide_has_quick_start(self, project_root):
        """Airflow guide should have quick start section."""
        guide_path = os.path.join(project_root, "docs", "guides", "airflow.md")
        with open(guide_path) as f:
            content = f.read()

        assert "Quick Start" in content or "Quickstart" in content, \
            "Guide should have quickstart section"
        assert "./lakehouse start airflow" in content, \
            "Guide should show how to start airflow"

    def test_airflow_guide_documents_dags(self, project_root):
        """Airflow guide should document included DAGs."""
        guide_path = os.path.join(project_root, "docs", "guides", "airflow.md")
        with open(guide_path) as f:
            content = f.read()

        # Should document the included DAGs
        assert "lakehouse_medallion_pipeline" in content
        assert "iceberg_maintenance" in content

    def test_airflow_guide_has_troubleshooting(self, project_root):
        """Airflow guide should have troubleshooting section."""
        guide_path = os.path.join(project_root, "docs", "guides", "airflow.md")
        with open(guide_path) as f:
            content = f.read()

        assert "Troubleshooting" in content, "Guide should have troubleshooting section"
