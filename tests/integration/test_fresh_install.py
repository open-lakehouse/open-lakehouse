"""Integration tests for fresh install validation.

Tests the lakehouse setup process and validates that a fresh clone
can successfully bootstrap all required components.
"""

import os
import subprocess
import pytest


@pytest.mark.integration
class TestCLIValidation:
    """Test lakehouse CLI syntax and basic functionality."""

    def test_lakehouse_script_syntax(self, lakehouse_cli):
        """Verify lakehouse script has valid bash syntax."""
        result = subprocess.run(
            ["bash", "-n", lakehouse_cli],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_lakehouse_help_command(self, lakehouse_cli):
        """Test lakehouse help command."""
        result = subprocess.run(
            [lakehouse_cli, "help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "lakehouse" in result.stdout.lower()
        assert "setup" in result.stdout
        assert "start" in result.stdout
        assert "status" in result.stdout

    def test_lakehouse_check_config_command(self, lakehouse_cli):
        """Test lakehouse check-config command exists."""
        result = subprocess.run(
            [lakehouse_cli, "help"],
            capture_output=True,
            text=True,
        )
        assert "check-config" in result.stdout

    def test_lakehouse_preflight_command(self, lakehouse_cli):
        """Test lakehouse preflight command exists."""
        result = subprocess.run(
            [lakehouse_cli, "help"],
            capture_output=True,
            text=True,
        )
        assert "preflight" in result.stdout

    def test_lakehouse_migrate_command(self, lakehouse_cli):
        """Test lakehouse migrate command exists."""
        result = subprocess.run(
            [lakehouse_cli, "help"],
            capture_output=True,
            text=True,
        )
        assert "migrate" in result.stdout


@pytest.mark.integration
class TestConfigurationFiles:
    """Test configuration file validation."""

    def test_env_example_exists(self, project_root):
        """Verify .env.example exists with required variables."""
        env_example = os.path.join(project_root, ".env.example")
        assert os.path.exists(env_example), ".env.example not found"

        with open(env_example, "r") as f:
            content = f.read()

        # Check required variables
        required_vars = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "S3_ENDPOINT",
        ]

        for var in required_vars:
            assert var in content, f"Missing {var} in .env.example"

    def test_spark_defaults_example_exists(self, project_root):
        """Verify spark-defaults.conf.example exists."""
        spark_conf = os.path.join(
            project_root, "config", "spark", "spark-defaults.conf.example"
        )
        assert os.path.exists(spark_conf), "spark-defaults.conf.example not found"

        with open(spark_conf, "r") as f:
            content = f.read()

        # Check required Spark configs
        required_configs = [
            "spark.sql.catalog.iceberg",
            "spark.sql.extensions",
            "spark.hadoop.fs.s3a.endpoint",
            "spark.jars",
        ]

        for config in required_configs:
            assert config in content, f"Missing {config} in spark-defaults.conf.example"

    def test_docker_compose_files_exist(self, project_root):
        """Verify all Docker Compose files exist."""
        compose_files = [
            "docker-compose-spark41.yml",
            "docker-compose-kafka.yml",
            "docker-compose-unity-catalog.yml",
            "docker-compose-mlflow.yml",
            "docker-compose-airflow.yml",
        ]

        for compose_file in compose_files:
            path = os.path.join(project_root, compose_file)
            assert os.path.exists(path), f"Missing {compose_file}"


@pytest.mark.integration
class TestDockerComposeValidation:
    """Test Docker Compose configuration validation."""

    def test_compose_spark41_valid(self, project_root):
        """Validate docker-compose-spark41.yml syntax."""
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose-spark41.yml",
                "config",
                "--quiet",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "COMPOSE_PROJECT_NAME": "test"},
        )
        assert result.returncode == 0 or "env file" in result.stderr.lower()

    def test_compose_kafka_valid(self, project_root):
        """Validate docker-compose-kafka.yml syntax."""
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose-kafka.yml", "config", "--quiet"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "COMPOSE_PROJECT_NAME": "test"},
        )
        assert result.returncode == 0 or "env file" in result.stderr.lower()


@pytest.mark.integration
class TestJARDownloadScript:
    """Test JAR download script functionality."""

    def test_download_script_exists(self, project_root):
        """Verify download-jars.sh exists."""
        script_path = os.path.join(project_root, "scripts", "tools", "download-jars.sh")
        assert os.path.exists(script_path), "download-jars.sh not found"

    def test_download_script_syntax(self, project_root):
        """Verify download-jars.sh has valid bash syntax."""
        script_path = os.path.join(project_root, "scripts", "tools", "download-jars.sh")
        result = subprocess.run(
            ["bash", "-n", script_path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_download_script_has_verify_flag(self, project_root):
        """Verify download-jars.sh supports --verify-only flag."""
        script_path = os.path.join(project_root, "scripts", "tools", "download-jars.sh")

        with open(script_path, "r") as f:
            content = f.read()

        assert "--verify-only" in content, "Missing --verify-only flag support"

    def test_download_script_has_retry_logic(self, project_root):
        """Verify download-jars.sh has retry logic."""
        script_path = os.path.join(project_root, "scripts", "tools", "download-jars.sh")

        with open(script_path, "r") as f:
            content = f.read()

        assert "retry" in content.lower() or "attempt" in content.lower(), (
            "Missing retry logic"
        )


@pytest.mark.integration
class TestPythonEnvironment:
    """Test Python environment setup."""

    def test_pyproject_toml_exists(self, project_root):
        """Verify pyproject.toml exists."""
        path = os.path.join(project_root, "pyproject.toml")
        assert os.path.exists(path), "pyproject.toml not found"

    def test_poetry_lock_exists(self, project_root):
        """Verify poetry.lock exists."""
        path = os.path.join(project_root, "poetry.lock")
        assert os.path.exists(path), "poetry.lock not found"

    def test_required_dependencies_in_pyproject(self, project_root):
        """Verify required dependencies are in pyproject.toml."""
        path = os.path.join(project_root, "pyproject.toml")

        with open(path, "r") as f:
            content = f.read()

        required_deps = ["pyspark", "pytest"]

        for dep in required_deps:
            assert dep in content, f"Missing {dep} in pyproject.toml"


@pytest.mark.integration
class TestDirectoryStructure:
    """Test required directory structure."""

    def test_required_directories_exist(self, project_root):
        """Verify required directories exist or can be created."""
        required_dirs = [
            "config/spark",
            "scripts",
            "tests",
        ]

        for dir_path in required_dirs:
            full_path = os.path.join(project_root, dir_path)
            assert os.path.isdir(full_path), f"Missing directory: {dir_path}"

    def test_jars_directory_creatable(self, project_root):
        """Verify jars directory exists or can be created."""
        jars_path = os.path.join(project_root, "jars")
        # Either exists or parent is writable
        if not os.path.exists(jars_path):
            assert os.access(project_root, os.W_OK), "Cannot create jars directory"


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndSetup:
    """Test end-to-end setup process with real services."""

    def test_postgres_catalog_tables(self, postgres_container):
        """Verify Iceberg catalog tables can be created in PostgreSQL."""
        import psycopg2

        host = postgres_container.get_container_host_ip()
        port = postgres_container.get_exposed_port(5432)

        conn = psycopg2.connect(
            host=host,
            port=port,
            user="iceberg",
            password="iceberg",
            database="iceberg_catalog",
        )

        cursor = conn.cursor()

        # Create migrations tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Verify table exists
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = '_migrations'
        """)
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        assert result is not None
        assert result[0] == "_migrations"
