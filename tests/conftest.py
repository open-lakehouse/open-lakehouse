"""Pytest configuration and shared fixtures for lakehouse-stack tests."""

import os
import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark():
    """Create a SparkSession for testing.

    Uses local mode with minimal resources to keep tests fast.
    Session is shared across all tests for efficiency.
    """
    session = (
        SparkSession.builder.appName("lakehouse-tests")
        .master("local[2]")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture(scope="session")
def data_path():
    """Return the path to test data.

    Detects whether running in Docker Jupyter or locally.
    """
    if os.path.exists("/home/jovyan/data"):
        return "/home/jovyan/data"
    elif os.path.exists("data"):
        return "data"
    else:
        return os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture(scope="session")
def sample_orders(spark, data_path):
    """Load a sample of order events for testing.

    Uses 1-day sample for speed. Falls back to 90-day if 1-day not available.
    """
    from pyspark.sql import functions as f

    orders_1d = os.path.join(data_path, "events", "orders_1d.parquet")
    orders_90d = os.path.join(data_path, "events", "orders_90d.parquet")

    df = None
    if os.path.exists(orders_1d):
        df = spark.read.parquet(orders_1d)
    elif os.path.exists(orders_90d):
        # Take a small sample for testing
        df = spark.read.parquet(orders_90d).limit(10000)

    if df is None:
        pytest.skip("No order data available")
        return None  # Never reached, but satisfies type checker

    # Add parsed timestamp
    return df.withColumn(
        "event_timestamp", f.to_timestamp(f.regexp_replace("ts", "T", " "))
    )


@pytest.fixture(scope="session")
def dim_brands(spark, data_path):
    """Load brands dimension table."""
    path = os.path.join(data_path, "dimensions", "brands.parquet")
    if not os.path.exists(path):
        pytest.skip("Brands dimension not available")
    return spark.read.parquet(path)


@pytest.fixture(scope="session")
def dim_locations(spark, data_path):
    """Load locations dimension table."""
    path = os.path.join(data_path, "dimensions", "locations.parquet")
    if not os.path.exists(path):
        pytest.skip("Locations dimension not available")
    return spark.read.parquet(path)
