"""Pytest fixtures for integration tests.

UC-only mode: catalog auth is handled by the Unity Catalog OSS server,
not by Spark configuration. These fixtures provide:

- An isolated PostgreSQL container (UC OSS backing store)
- An isolated Kafka container
- A SparkSession with a filesystem-based Iceberg catalog (hadoop catalog)
  for tests that don't need UC

Tests that require UC OSS itself should skip when no UC server is reachable
(check `http://localhost:8081/api/2.1/unity-catalog/catalogs`).
"""

import os
import time
from typing import Generator

import pytest

try:
    from testcontainers.kafka import KafkaContainer
    from testcontainers.postgres import PostgresContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    PostgresContainer = None
    KafkaContainer = None


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (may require Docker)"
    )
    config.addinivalue_line("markers", "slow: mark test as slow-running")


@pytest.fixture(scope="session")
def docker_available() -> bool:
    import subprocess

    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture(scope="session", autouse=True)
def composed_storage(docker_available):
    """Ensure the Composed storage layer (SeaweedFS + PostgreSQL) is up.

    PR #13 / T-1.20d: storage moved from host-installed into Compose
    (docker-compose-storage.yml). The lifecycle / E-07 tests reach it via the
    published host ports (localhost:5432 / :8333) with run-scoped names, so it
    must be running or those tests would silently skip (a skip does not count as
    a pass, §1.17.8). Idempotent: only starts storage when the ports are not
    already listening, and never tears the shared stack down.
    """
    import os
    import socket
    import subprocess

    if not docker_available:
        yield False
        return

    def _listening(port: int) -> bool:
        with socket.socket() as s:
            s.settimeout(1)
            return s.connect_ex(("localhost", port)) == 0

    if not (_listening(5432) and _listening(8333)):
        root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        subprocess.run(
            [os.path.join(root, "lakehouse"), "start", "storage"],
            cwd=root,
            capture_output=True,
            timeout=180,
        )
    yield True


@pytest.fixture(scope="session")
def postgres_container(docker_available) -> Generator:
    """Isolated PostgreSQL — used as Unity Catalog's backing store."""
    if not docker_available:
        pytest.skip("Docker not available")
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip("testcontainers not installed")

    container = PostgresContainer(
        image="postgres:16",
        username="uc",
        password="uc",
        dbname="unity_catalog",
    )
    try:
        container.start()
        time.sleep(2)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def kafka_container(docker_available) -> Generator:
    if not docker_available:
        pytest.skip("Docker not available")
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip("testcontainers not installed")

    container = KafkaContainer(image="confluentinc/cp-kafka:7.5.0")
    try:
        container.start()
        time.sleep(5)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def kafka_bootstrap_servers(kafka_container) -> str:
    return kafka_container.get_bootstrap_server()


@pytest.fixture(scope="session")
def spark_local(clean_warehouse_session):
    """SparkSession with a hadoop (filesystem) Iceberg catalog.

    No JDBC, no UC server required. Use for table-format and SQL-level tests
    that don't need a real catalog service. Tests requiring UC OSS itself
    should check for a live UC endpoint and skip otherwise.
    """
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("open-lakehouse-tests")
        .master("local[2]")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.iceberg.type", "hadoop")
        .config("spark.sql.catalog.iceberg.warehouse", clean_warehouse_session)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    yield spark
    spark.stop()


@pytest.fixture(scope="session")
def clean_warehouse_session(tmp_path_factory):
    return str(tmp_path_factory.mktemp("iceberg-warehouse"))


@pytest.fixture(scope="function")
def clean_warehouse(tmp_path):
    warehouse_path = tmp_path / "warehouse"
    warehouse_path.mkdir(parents=True, exist_ok=True)
    return str(warehouse_path)


@pytest.fixture(scope="session")
def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def lakehouse_cli(project_root) -> str:
    return os.path.join(project_root, "lakehouse")
