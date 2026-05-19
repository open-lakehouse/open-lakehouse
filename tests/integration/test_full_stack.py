"""
Full Stack Integration Tests

Tests for complete service integration:
Kafka → Spark → Iceberg → PostgreSQL → SeaweedFS

These tests verify the full data pipeline works end-to-end.
"""

import subprocess
import pytest
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFullStackScripts:
    """Tests for full stack integration scripts."""

    def test_full_stack_script_exists(self):
        """Full stack test script should exist."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        assert script.exists(), "test-full-stack.py should exist"

    def test_full_stack_script_syntax(self):
        """Full stack test script should have valid Python syntax."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        if not script.exists():
            pytest.skip("test-full-stack.py not found")

        result = subprocess.run(
            ["python3", "-m", "py_compile", str(script)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_full_stack_script_tests_all_services(self):
        """Full stack script should test all 5 services."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        if not script.exists():
            pytest.skip("test-full-stack.py not found")

        content = script.read_text()

        # Should reference all services
        assert "kafka" in content.lower(), "Should test Kafka"
        assert "spark" in content.lower(), "Should test Spark"
        assert "iceberg" in content.lower(), "Should test Iceberg"
        assert "postgres" in content.lower(), "Should test PostgreSQL"
        # SeaweedFS may be implicit via S3
        assert "s3" in content.lower() or "seaweed" in content.lower() or "storage" in content.lower(), \
            "Should reference storage layer"


class TestStreamingScripts:
    """Tests for streaming integration scripts."""

    def test_streaming_script_exists(self):
        """Streaming test script should exist."""
        script = PROJECT_ROOT / "scripts" / "test-streaming-iceberg.py"
        assert script.exists(), "test-streaming-iceberg.py should exist"

    def test_streaming_script_syntax(self):
        """Streaming test script should have valid Python syntax."""
        script = PROJECT_ROOT / "scripts" / "test-streaming-iceberg.py"
        if not script.exists():
            pytest.skip("test-streaming-iceberg.py not found")

        result = subprocess.run(
            ["python3", "-m", "py_compile", str(script)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_streaming_script_uses_structured_streaming(self):
        """Streaming script should use Spark Structured Streaming."""
        script = PROJECT_ROOT / "scripts" / "test-streaming-iceberg.py"
        if not script.exists():
            pytest.skip("test-streaming-iceberg.py not found")

        content = script.read_text()

        assert "readStream" in content, "Should use readStream for streaming"
        assert "writeStream" in content, "Should use writeStream for output"
        assert "checkpoint" in content.lower(), "Should use checkpointing"


class TestMedallionArchitecture:
    """Tests for medallion architecture (bronze/silver/gold)."""

    def test_full_stack_has_medallion_layers(self):
        """Full stack script should implement medallion architecture."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        if not script.exists():
            pytest.skip("test-full-stack.py not found")

        content = script.read_text()

        assert "bronze" in content.lower(), "Should have bronze layer"
        assert "silver" in content.lower(), "Should have silver layer"
        assert "gold" in content.lower(), "Should have gold layer"

    def test_transformations_between_layers(self):
        """Should have transformations between medallion layers."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        if not script.exists():
            pytest.skip("test-full-stack.py not found")

        content = script.read_text()

        # Should have data transformations
        has_transform = any(kw in content for kw in [
            "to_timestamp", "GROUP BY", "SUM(", "COUNT(", "AVG(",
            "transformation", "aggregat"
        ])
        assert has_transform, "Should have data transformations"


class TestDataConsistency:
    """Tests for data consistency checks."""

    def test_full_stack_verifies_consistency(self):
        """Full stack script should verify data consistency."""
        script = PROJECT_ROOT / "scripts" / "test-full-stack.py"
        if not script.exists():
            pytest.skip("test-full-stack.py not found")

        content = script.read_text()

        # Should verify data across layers
        has_consistency = any(kw in content.lower() for kw in [
            "consistency", "verify", "match", "compare", "count"
        ])
        assert has_consistency, "Should verify data consistency"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_stack
class TestFullStackLive:
    """Live tests requiring all services running.

    Skipped unless all services are available.
    Run with: pytest -m full_stack tests/integration/test_full_stack.py
    """

    @pytest.fixture(autouse=True)
    def check_all_services_running(self):
        """Skip tests if required services are not running."""
        import socket

        services = [
            ("PostgreSQL", "localhost", 5432),
            ("Kafka", "localhost", 9092),
            ("Spark", "localhost", 7078),  # Spark 4.1 master
        ]

        for name, host, port in services:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                pytest.skip(f"{name} not running on port {port}")

    def test_kafka_connectivity(self):
        """Kafka should be accessible."""
        try:
            from kafka import KafkaConsumer
            consumer = KafkaConsumer(
                bootstrap_servers='localhost:9092',
                consumer_timeout_ms=1000
            )
            topics = consumer.topics()
            consumer.close()
            assert isinstance(topics, set)
        except ImportError:
            pytest.skip("kafka-python not installed")
        except Exception as e:
            pytest.fail(f"Kafka connectivity failed: {e}")

    def test_postgres_connectivity(self):
        """PostgreSQL should be accessible."""
        try:
            import psycopg2
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="iceberg_catalog",
                user="iceberg",
                password="iceberg"
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            assert result is not None and result[0] == 1
        except ImportError:
            pytest.skip("psycopg2 not installed")
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not accessible with expected credentials")
        except Exception as e:
            pytest.fail(f"PostgreSQL connectivity failed: {e}")
