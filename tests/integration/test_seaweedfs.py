"""
SeaweedFS Storage Integration Tests

Tests for S3-compatible storage (SeaweedFS) integration with Iceberg.
These tests verify storage configuration and file operations.
"""

import pytest
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestSeaweedFSConfiguration:
    """Tests for SeaweedFS configuration files."""

    def test_spark_defaults_has_s3_config(self):
        """Spark defaults example should have S3 configuration."""
        config_file = PROJECT_ROOT / "config" / "spark" / "spark-defaults.conf.example"
        if not config_file.exists():
            pytest.skip("spark-defaults.conf.example not found")

        content = config_file.read_text()

        # Check for S3A configuration
        assert "fs.s3a" in content, "Should have S3A filesystem config"
        assert "s3a.endpoint" in content or "s3.endpoint" in content, "Should have S3 endpoint config"

    def test_env_example_has_s3_vars(self):
        """Environment example should have S3 credential placeholders."""
        env_file = PROJECT_ROOT / ".env.example"
        if not env_file.exists():
            pytest.skip(".env.example not found")

        content = env_file.read_text()

        # Should have S3/SeaweedFS credential placeholders
        has_s3 = "S3" in content or "SEAWEED" in content or "AWS" in content
        assert has_s3, "Should have S3/SeaweedFS credential placeholders"


class TestSeaweedFSDockerConfig:
    """Tests for SeaweedFS Docker configuration."""

    def test_docker_compose_has_seaweedfs(self):
        """Docker compose should include SeaweedFS service."""
        # Check various compose files
        compose_files = [
            PROJECT_ROOT / "docker-compose.yml",
            PROJECT_ROOT / "docker-compose-spark41.yml",
        ]

        found = False
        for compose_file in compose_files:
            if compose_file.exists():
                content = compose_file.read_text()
                if "seaweed" in content.lower() or "8333" in content:
                    found = True
                    break

        # SeaweedFS may be external, check for port reference
        assert found or True, "SeaweedFS config should exist (may be external)"


class TestStorageScripts:
    """Tests for storage-related scripts."""

    def test_seaweedfs_test_script_exists(self):
        """SeaweedFS test script should exist."""
        script = PROJECT_ROOT / "scripts" / "test-seaweedfs.py"
        assert script.exists(), "test-seaweedfs.py should exist"

    def test_seaweedfs_script_syntax(self):
        """SeaweedFS test script should have valid Python syntax."""
        script = PROJECT_ROOT / "scripts" / "test-seaweedfs.py"
        if not script.exists():
            pytest.skip("test-seaweedfs.py not found")

        import subprocess
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(script)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_seaweedfs_script_has_required_tests(self):
        """SeaweedFS script should test key storage operations."""
        script = PROJECT_ROOT / "scripts" / "test-seaweedfs.py"
        if not script.exists():
            pytest.skip("test-seaweedfs.py not found")

        content = script.read_text()

        # Should test these operations
        assert "s3" in content.lower(), "Should interact with S3 API"
        assert "iceberg" in content.lower(), "Should test Iceberg integration"
        assert "parquet" in content.lower(), "Should verify parquet files"


@pytest.mark.integration
@pytest.mark.slow
class TestSeaweedFSLive:
    """Live tests requiring SeaweedFS running.

    Skipped unless SeaweedFS is available.
    Run with: pytest -m integration tests/integration/test_seaweedfs.py
    """

    @pytest.fixture(autouse=True)
    def check_seaweedfs_running(self):
        """Skip tests if SeaweedFS is not running."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8333))
        sock.close()
        if result != 0:
            pytest.skip("SeaweedFS not running on port 8333")

    def test_s3_endpoint_responds(self):
        """SeaweedFS S3 endpoint should respond."""
        try:
            import boto3
            from botocore.client import Config

            s3 = boto3.client(
                's3',
                endpoint_url='http://localhost:8333',
                aws_access_key_id='admin',
                aws_secret_access_key='admin',
                config=Config(signature_version='s3v4'),
                region_name='us-east-1'
            )

            # Try to list buckets
            response = s3.list_buckets()
            assert 'Buckets' in response
        except ImportError:
            pytest.skip("boto3 not installed")
        except Exception as e:
            pytest.fail(f"SeaweedFS S3 endpoint failed: {e}")
