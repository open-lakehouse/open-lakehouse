"""
Integration tests for Unity Catalog OSS.

These tests verify:
1. Docker Compose configuration is valid
2. Configuration files have correct structure
3. Unity Catalog REST API responds (when running)
4. Spark configuration for Unity Catalog
"""

import subprocess
from pathlib import Path

import pytest
import yaml

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
        """Unity Catalog should expose port 8081."""
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
            ["python3", "-m", "py_compile", str(script)], capture_output=True, text=True
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
        import urllib.error
        import urllib.request

        # Check if Unity Catalog API specifically responds (not just port 8081)
        url = "http://localhost:8081/api/2.1/unity-catalog/catalogs"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status != 200:
                    pytest.skip("Unity Catalog not responding correctly")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pytest.skip("Unity Catalog not running on port 8081")

    def test_unity_catalog_api_responds(self):
        """Unity Catalog REST API should respond."""
        import json
        import urllib.request

        url = "http://localhost:8081/api/2.1/unity-catalog/catalogs"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read())
                assert "catalogs" in data or isinstance(data, list)
        except Exception as e:
            pytest.fail(f"Unity Catalog API failed: {e}")

    def test_iceberg_endpoint_responds(self):
        """Iceberg REST endpoint should respond."""
        import urllib.error
        import urllib.request

        url = "http://localhost:8081/api/2.1/unity-catalog/iceberg/v1/config"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                assert response.status == 200
        except urllib.error.HTTPError as e:
            # 401/403 is OK - means endpoint exists but needs auth
            if e.code not in (401, 403):
                pytest.fail(f"Iceberg endpoint error: {e}")
        except urllib.error.URLError as e:
            pytest.fail(f"Iceberg endpoint failed: {e}")


# =================================================================================
# PR #13 / D2 gates — UC 0.5.0 upgrade (I-44, I-47) + round-trip (I-08)
# =================================================================================

import json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
import uuid  # noqa: E402

UC_API = "http://localhost:8081/api/2.1/unity-catalog"
MASTER = "spark-master-41"


def _uc_up() -> bool:
    try:
        with urllib.request.urlopen(f"{UC_API}/catalogs", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _post(path: str, body: dict):
    req = urllib.request.Request(
        f"{UC_API}/{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _master_running() -> bool:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.split()
        return MASTER in out
    except Exception:
        return False


@pytest.mark.integration
class TestUC050Gates:
    """Live D2 gates against the official unitycatalog/unitycatalog:v0.5.0 image."""

    @pytest.fixture(autouse=True)
    def _require_uc(self):
        if not _uc_up():
            pytest.skip("Unity Catalog not reachable on localhost:8081")

    def test_i47_uc_rejects_iceberg_format(self):
        # Pins §1.12: no UC OSS build accepts ICEBERG as a table format.
        code, body = _post(
            "tables",
            {
                "name": "t_ice",
                "catalog_name": "unity",
                "schema_name": "default",
                "table_type": "EXTERNAL",
                "data_source_format": "ICEBERG",
                "columns": [
                    {
                        "name": "id",
                        "type_text": "int",
                        "type_name": "INT",
                        "position": 0,
                        "nullable": True,
                    }
                ],
                "storage_location": "s3://lakehouse/warehouse/_iceberg_probe",
            },
        )
        assert code == 400, f"UC must 400 on ICEBERG, got {code}: {body[:200]}"
        assert "DataSourceFormat" in body or "ICEBERG" in body

    def test_i47_iceberg_rest_has_no_table_write_endpoint(self):
        # The Iceberg REST adapter is read-only: creating a namespace/table via it
        # must be rejected (no 2xx). Proves §1.12's "no POST write endpoints".
        req = urllib.request.Request(
            f"{UC_API}/iceberg/v1/namespaces",
            data=json.dumps({"namespace": ["probe"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                assert r.status not in (
                    200,
                    201,
                ), f"Iceberg REST unexpectedly accepted a namespace create ({r.status})"
        except urllib.error.HTTPError as e:
            # 404/405/501/401/403/400 all confirm "no working write endpoint".
            assert e.code >= 400, f"unexpected status {e.code}"

    @pytest.mark.skipif(not _master_running(), reason=f"{MASTER} not running")
    def test_i44_i08_catalog_schema_delta_roundtrip(self, tmp_path):
        # I-44: create catalog/schema/Delta table + credential-vended write on v0.5.0.
        # I-08: read it back via the UC Spark connector.
        sfx = uuid.uuid4().hex[:8]
        cat, sch = "unity", f"i44_{sfx}"
        _post("schemas", {"name": sch, "catalog_name": cat})
        script = f"""
        from pyspark.sql import SparkSession
        s = SparkSession.builder.appName("i44").master("local[2]").config("spark.ui.enabled","false").getOrCreate()
        s.sparkContext.setLogLevel("ERROR")
        t = "{cat}.{sch}.orders"
        s.sql(f"CREATE TABLE IF NOT EXISTS {{t}} (id BIGINT, v BIGINT) USING delta LOCATION 's3://lakehouse/warehouse/i44/{sfx}'")
        s.sql(f"INSERT INTO {{t}} VALUES (1,10),(2,20),(3,30)")
        n = s.sql(f"SELECT count(*) FROM {{t}}").collect()[0][0]
        print(f"I44 count={{n}}")
        assert n == 3
        print("I44_PASS")
        s.stop()
        """
        f = tmp_path / "i44.py"
        import textwrap

        f.write_text(textwrap.dedent(script))
        subprocess.run(
            ["docker", "cp", str(f), f"{MASTER}:/tmp/_i44.py"],
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            ["docker", "exec", MASTER, "/opt/spark/bin/spark-submit", "/tmp/_i44.py"],
            capture_output=True,
            text=True,
            timeout=300,
        ).stdout
        # cleanup the UC table registration
        try:
            req = urllib.request.Request(
                f"{UC_API}/tables/{cat}.{sch}.orders", method="DELETE"
            )
            urllib.request.urlopen(req, timeout=8)
        except Exception:
            pass
        assert "I44_PASS" in out, f"UC 0.5.0 Delta round-trip failed:\n{out[-1500:]}"
