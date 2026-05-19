"""
Integration tests for Unity Catalog OSS.

These tests verify:
1. Docker Compose configuration is valid
2. Configuration files have correct structure
3. Unity Catalog REST API responds (when running)
4. Spark configuration for Unity Catalog
"""

import subprocess
import pytest
import yaml
from pathlib import Path

# Root directory of the project
ROOT_DIR = Path(__file__).parent.parent.parent


class TestUnityCatalogConfiguration:
    """Tests for Unity Catalog configuration files."""

    def test_docker_compose_file_exists(self):
        """Docker Compose file for Unity Catalog should exist."""
        compose_file = ROOT_DIR / "docker-compose-unity-catalog.yml"
        assert compose_file.exists(), "docker-compose-unity-catalog.yml not found"

    def test_docker_compose_valid_yaml(self):
        """Docker Compose file should be valid YAML."""
        compose_file = ROOT_DIR / "docker-compose-unity-catalog.yml"
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        assert "services" in config
        assert "unity-catalog" in config["services"]

    def test_docker_compose_has_healthcheck(self):
        """Unity Catalog service should have a healthcheck."""
        compose_file = ROOT_DIR / "docker-compose-unity-catalog.yml"
        with open(compose_file) as f:
            config = yaml.safe_load(f)

        uc_service = config["services"]["unity-catalog"]
        assert "healthcheck" in uc_service, "Unity Catalog should have healthcheck"
        assert "test" in uc_service["healthcheck"]

    def test_docker_compose_port_mapping(self):
        """Unity Catalog should expose port 8080."""
        compose_file = ROOT_DIR / "docker-compose-unity-catalog.yml"
        with open(compose_file) as f:
            config = yaml.safe_load(f)

        uc_service = config["services"]["unity-catalog"]
        assert "ports" in uc_service
        # Ports can be strings like "8080:8080" or dicts
        port_8080_mapped = any("8080" in str(p) for p in uc_service["ports"])
        assert port_8080_mapped, "Port 8080 should be mapped"

    def test_server_properties_example_exists(self):
        """Server properties example should exist."""
        props_file = ROOT_DIR / "config" / "unity-catalog" / "server.properties.example"
        assert props_file.exists(), "server.properties.example not found"

    def test_server_properties_has_required_sections(self):
        """Server properties should have S3 and server configuration."""
        props_file = ROOT_DIR / "config" / "unity-catalog" / "server.properties.example"
        content = props_file.read_text()

        # Check for required configuration sections
        assert "server.port" in content, "Should have server port config"
        assert "s3.bucketPath" in content, "Should have S3 bucket path"
        assert "s3.accessKey" in content, "Should have S3 access key placeholder"
        assert "s3.secretKey" in content, "Should have S3 secret key placeholder"
        assert "s3.endpoint" in content, "Should have S3 endpoint for SeaweedFS"

    def test_spark_defaults_example_exists(self):
        """Spark defaults example should exist (UC-wired)."""
        spark_file = ROOT_DIR / "config" / "spark" / "spark-defaults.conf.example"
        assert spark_file.exists(), "spark-defaults.conf.example not found"

    def test_spark_defaults_has_rest_catalog_config(self):
        """Spark config should use RESTCatalog for Unity Catalog."""
        spark_file = ROOT_DIR / "config" / "spark" / "spark-defaults.conf.example"
        content = spark_file.read_text()

        # Check for REST catalog configuration
        assert "RESTCatalog" in content, "Should configure RESTCatalog"
        assert "unity-catalog/iceberg" in content, "Should have UC Iceberg endpoint"


class TestUnityCatalogDocumentation:
    """Tests for Unity Catalog documentation."""

    def test_unity_catalog_guide_exists(self):
        """Unity Catalog guide should exist."""
        guide = ROOT_DIR / "docs" / "guides" / "unity-catalog.md"
        assert guide.exists(), "unity-catalog.md guide not found"

    def test_guide_has_quick_start(self):
        """Guide should have quick start section."""
        guide = ROOT_DIR / "docs" / "guides" / "unity-catalog.md"
        content = guide.read_text()

        assert "Quick Start" in content, "Should have Quick Start section"
        assert "lakehouse start unity-catalog" in content, "Should show start command"

    def test_guide_has_troubleshooting(self):
        """Guide should have troubleshooting section."""
        guide = ROOT_DIR / "docs" / "guides" / "unity-catalog.md"
        content = guide.read_text()

        assert "Troubleshooting" in content, "Should have Troubleshooting section"


class TestUnityCatalogCLI:
    """Tests for lakehouse CLI Unity Catalog support."""

    def test_lakehouse_cli_has_uc_commands(self):
        """Lakehouse CLI should support unity-catalog commands."""
        lakehouse_cli = ROOT_DIR / "lakehouse"
        content = lakehouse_cli.read_text()

        # Check for unity-catalog support in start/stop
        assert "unity-catalog" in content, "CLI should support unity-catalog"
        assert "unity-catalog|uc" in content, "CLI should support 'uc' shorthand"

    def test_lakehouse_cli_starts_unity_catalog(self):
        """CLI start command should handle unity-catalog."""
        lakehouse_cli = ROOT_DIR / "lakehouse"
        content = lakehouse_cli.read_text()

        # Should use docker compose for unity-catalog
        assert "docker-compose-unity-catalog.yml" in content


class TestUnityCatalogDemoScript:
    """Tests for Unity Catalog demo script."""

    def test_demo_script_exists(self):
        """Demo script should exist."""
        script = ROOT_DIR / "scripts" / "unity_catalog_demo.py"
        assert script.exists(), "unity_catalog_demo.py not found"

    def test_demo_script_syntax_valid(self):
        """Demo script should have valid Python syntax."""
        script = ROOT_DIR / "scripts" / "unity_catalog_demo.py"
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(script)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_demo_script_has_spark_session(self):
        """Demo script should create SparkSession."""
        script = ROOT_DIR / "scripts" / "unity_catalog_demo.py"
        content = script.read_text()

        assert "SparkSession" in content, "Should use SparkSession"
        assert "RESTCatalog" in content, "Should configure RESTCatalog"

    def test_demo_script_creates_medallion_schemas(self):
        """Demo script should create medallion architecture schemas."""
        script = ROOT_DIR / "scripts" / "unity_catalog_demo.py"
        content = script.read_text()

        assert "bronze" in content, "Should create bronze schema"
        assert "silver" in content, "Should create silver schema"
        assert "gold" in content, "Should create gold schema"


@pytest.mark.integration
@pytest.mark.slow
class TestUnityCatalogLive:
    """Live tests that require Unity Catalog running.

    These tests are skipped unless Unity Catalog is available.
    Run with: pytest -m integration tests/integration/test_unity_catalog.py
    """

    @pytest.fixture(autouse=True)
    def check_unity_catalog_running(self):
        """Skip tests if Unity Catalog is not running."""
        import urllib.request
        import urllib.error

        # Check if Unity Catalog API specifically responds (not just port 8080)
        url = "http://localhost:8080/api/2.1/unity-catalog/catalogs"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status != 200:
                    pytest.skip("Unity Catalog not responding correctly")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pytest.skip("Unity Catalog not running on port 8080")

    def test_unity_catalog_api_responds(self):
        """Unity Catalog REST API should respond."""
        import urllib.request
        import json

        url = "http://localhost:8080/api/2.1/unity-catalog/catalogs"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read())
                assert "catalogs" in data or isinstance(data, list)
        except Exception as e:
            pytest.fail(f"Unity Catalog API failed: {e}")

    def test_iceberg_endpoint_responds(self):
        """Iceberg REST endpoint should respond."""
        import urllib.request
        import urllib.error

        url = "http://localhost:8080/api/2.1/unity-catalog/iceberg/v1/config"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                assert response.status == 200
        except urllib.error.HTTPError as e:
            # 401/403 is OK - means endpoint exists but needs auth
            if e.code not in (401, 403):
                pytest.fail(f"Iceberg endpoint error: {e}")
        except urllib.error.URLError as e:
            pytest.fail(f"Iceberg endpoint failed: {e}")
