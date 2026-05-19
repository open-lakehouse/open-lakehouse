#!/usr/bin/env python3
"""
Unity Catalog Live Integration Test

Tests Unity Catalog OSS with live services:
- Unity Catalog REST API operations
- Spark with RESTCatalog configuration
- Table creation via UC REST
- Data operations via Spark
- Cross-client access (curl verification)

Prerequisites:
    ./lakehouse start unity-catalog
    # Or: ./lakehouse start all && ./lakehouse start unity-catalog

Usage:
    # Direct Python (uses requests for REST API)
    python scripts/test-unity-catalog-live.py

    # Via spark-submit (requires UC-configured Spark)
    docker exec spark-master-41 /opt/spark/bin/spark-submit /scripts/test-unity-catalog-live.py
"""

import sys
import json
import subprocess
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not installed. Using curl fallback.")

from pyspark.sql import SparkSession
from pyspark.sql import functions as f


# Configuration
UC_HOST = "localhost"
UC_PORT = 8080
UC_BASE_URL = f"http://{UC_HOST}:{UC_PORT}"
UC_API_URL = f"{UC_BASE_URL}/api/2.1/unity-catalog"
UC_ICEBERG_URL = f"{UC_BASE_URL}/api/2.1/unity-catalog/iceberg"

# Test catalog/schema/table names
TEST_CATALOG = "unity"
TEST_SCHEMA = "test_live"
TEST_TABLE = "orders"


def check_uc_health():
    """Check if Unity Catalog is running and healthy."""
    print("\n" + "=" * 60)
    print("Test 1: Unity Catalog Health Check")
    print("=" * 60)

    url = f"{UC_API_URL}/catalogs"

    if REQUESTS_AVAILABLE:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                catalogs = data.get('catalogs', [])
                print(f"  Unity Catalog is running")
                print(f"  Catalogs: {[c.get('name') for c in catalogs]}")
                print("  ✅ Health check passed")
                return True
            else:
                print(f"  ❌ Unexpected status: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Cannot connect to Unity Catalog at {UC_BASE_URL}")
            print("     Run: ./lakehouse start unity-catalog")
            return False
        except Exception as e:
            print(f"  ❌ Health check failed: {e}")
            return False
    else:
        # Fallback to curl
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout == "200":
                print("  ✅ Unity Catalog is running (curl check)")
                return True
            else:
                print(f"  ❌ Unity Catalog returned: {result.stdout}")
                return False
        except Exception as e:
            print(f"  ❌ Health check failed: {e}")
            return False


def test_rest_api_operations():
    """Test Unity Catalog REST API operations."""
    print("\n" + "=" * 60)
    print("Test 2: REST API Operations")
    print("=" * 60)

    if not REQUESTS_AVAILABLE:
        print("  SKIP: requests library not available")
        return False

    try:
        # List catalogs
        print("  Listing catalogs...")
        response = requests.get(f"{UC_API_URL}/catalogs")
        catalogs = response.json().get('catalogs', [])
        print(f"    Found {len(catalogs)} catalog(s)")

        # Check if unity catalog exists
        unity_exists = any(c.get('name') == TEST_CATALOG for c in catalogs)
        if not unity_exists:
            print(f"    Creating catalog: {TEST_CATALOG}")
            requests.post(f"{UC_API_URL}/catalogs", json={"name": TEST_CATALOG})

        # Create schema
        print(f"  Creating schema: {TEST_SCHEMA}")
        schema_url = f"{UC_API_URL}/schemas"
        response = requests.post(schema_url, json={
            "name": TEST_SCHEMA,
            "catalog_name": TEST_CATALOG,
        })
        if response.status_code in (200, 201, 409):  # 409 = already exists
            print(f"    Schema created/exists: {TEST_CATALOG}.{TEST_SCHEMA}")
        else:
            print(f"    ⚠️  Schema creation response: {response.status_code}")

        # List schemas
        print("  Listing schemas...")
        response = requests.get(f"{UC_API_URL}/schemas?catalog_name={TEST_CATALOG}")
        schemas = response.json().get('schemas', [])
        print(f"    Schemas in {TEST_CATALOG}: {[s.get('name') for s in schemas]}")

        print("  ✅ REST API operations successful")
        return True

    except Exception as e:
        print(f"  ❌ REST API operations failed: {e}")
        return False


def test_spark_with_uc(spark):
    """Test Spark operations using Unity Catalog as RESTCatalog."""
    print("\n" + "=" * 60)
    print("Test 3: Spark with Unity Catalog")
    print("=" * 60)

    try:
        # Check if Spark is configured for UC
        catalog_impl = spark.conf.get("spark.sql.catalog.iceberg.catalog-impl", "")
        if "RESTCatalog" not in catalog_impl:
            print("  ⚠️  Spark not configured for RESTCatalog")
            print("     Current config: " + catalog_impl)
            print("     Attempting to configure...")

            # Try to configure Spark for UC
            spark.conf.set("spark.sql.catalog.uc", "org.apache.iceberg.spark.SparkCatalog")
            spark.conf.set("spark.sql.catalog.uc.catalog-impl", "org.apache.iceberg.rest.RESTCatalog")
            spark.conf.set("spark.sql.catalog.uc.uri", UC_ICEBERG_URL)
            spark.conf.set("spark.sql.catalog.uc.warehouse", TEST_CATALOG)
            spark.conf.set("spark.sql.catalog.uc.token", "not_used")
            catalog_name = "uc"
        else:
            catalog_name = "iceberg"
            print(f"  Spark configured with RESTCatalog")

        # Create namespace
        print(f"  Creating namespace: {catalog_name}.{TEST_SCHEMA}")
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog_name}.{TEST_SCHEMA}")

        # Create table
        print(f"  Creating table: {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}")
        spark.sql(f"DROP TABLE IF EXISTS {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}")
        spark.sql(f"""
            CREATE TABLE {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE} (
                order_id STRING,
                customer_id STRING,
                product STRING,
                amount DOUBLE,
                order_date DATE
            ) USING iceberg
        """)

        # Insert data
        print("  Inserting test data...")
        spark.sql(f"""
            INSERT INTO {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE} VALUES
            ('UC-001', 'CUST-1', 'Widget', 99.99, DATE '2024-01-15'),
            ('UC-002', 'CUST-2', 'Gadget', 149.99, DATE '2024-01-16'),
            ('UC-003', 'CUST-1', 'Device', 299.99, DATE '2024-01-17')
        """)

        # Query data
        print("  Querying data...")
        count = spark.sql(f"SELECT COUNT(*) FROM {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}").collect()[0][0]
        print(f"    Row count: {count}")

        spark.sql(f"SELECT * FROM {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}").show()

        if count == 3:
            print("  ✅ Spark with Unity Catalog successful")
            return catalog_name
        else:
            print(f"  ❌ Expected 3 rows, got {count}")
            return None

    except Exception as e:
        print(f"  ❌ Spark with Unity Catalog failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_table_via_rest():
    """Verify table exists via REST API."""
    print("\n" + "=" * 60)
    print("Test 4: Verify Table via REST API")
    print("=" * 60)

    if not REQUESTS_AVAILABLE:
        print("  SKIP: requests library not available")
        return False

    try:
        # List tables in schema
        url = f"{UC_API_URL}/tables?catalog_name={TEST_CATALOG}&schema_name={TEST_SCHEMA}"
        response = requests.get(url)

        if response.status_code == 200:
            tables = response.json().get('tables', [])
            table_names = [t.get('name') for t in tables]
            print(f"  Tables in {TEST_CATALOG}.{TEST_SCHEMA}: {table_names}")

            if TEST_TABLE in table_names:
                print(f"  ✅ Table '{TEST_TABLE}' found via REST API")
                return True
            else:
                print(f"  ❌ Table '{TEST_TABLE}' not found")
                return False
        else:
            print(f"  ❌ Failed to list tables: {response.status_code}")
            return False

    except Exception as e:
        print(f"  ❌ REST verification failed: {e}")
        return False


def test_iceberg_metadata(spark, catalog_name):
    """Test Iceberg-specific metadata via Unity Catalog."""
    print("\n" + "=" * 60)
    print("Test 5: Iceberg Metadata via Unity Catalog")
    print("=" * 60)

    if not catalog_name:
        print("  SKIP: No catalog configured")
        return False

    try:
        table_ref = f"{catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}"

        # Check snapshots
        print("  Checking snapshots...")
        snapshots = spark.sql(f"SELECT * FROM {table_ref}.snapshots").collect()
        print(f"    Snapshots: {len(snapshots)}")

        # Check history
        print("  Checking history...")
        history = spark.sql(f"SELECT * FROM {table_ref}.history").collect()
        print(f"    History entries: {len(history)}")

        # Check files
        print("  Checking data files...")
        files = spark.sql(f"SELECT * FROM {table_ref}.files").collect()
        print(f"    Data files: {len(files)}")

        if snapshots and files:
            print("  ✅ Iceberg metadata accessible via Unity Catalog")
            return True
        else:
            print("  ❌ Metadata incomplete")
            return False

    except Exception as e:
        print(f"  ❌ Metadata check failed: {e}")
        return False


def test_schema_evolution(spark, catalog_name):
    """Test schema evolution via Unity Catalog."""
    print("\n" + "=" * 60)
    print("Test 6: Schema Evolution")
    print("=" * 60)

    if not catalog_name:
        print("  SKIP: No catalog configured")
        return False

    try:
        table_ref = f"{catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}"

        # Add column
        print("  Adding column 'status'...")
        spark.sql(f"ALTER TABLE {table_ref} ADD COLUMN status STRING")

        # Verify column added
        columns = spark.sql(f"DESCRIBE {table_ref}").collect()
        col_names = [c['col_name'] for c in columns]
        print(f"    Columns: {col_names}")

        if 'status' in col_names:
            # Update with new column
            print("  Updating records with status...")
            spark.sql(f"UPDATE {table_ref} SET status = 'completed' WHERE order_id = 'UC-001'")
            spark.sql(f"UPDATE {table_ref} SET status = 'pending' WHERE status IS NULL")

            spark.sql(f"SELECT order_id, product, status FROM {table_ref}").show()
            print("  ✅ Schema evolution successful")
            return True
        else:
            print("  ❌ Column 'status' not added")
            return False

    except Exception as e:
        print(f"  ❌ Schema evolution failed: {e}")
        return False


def cleanup(spark, catalog_name):
    """Clean up test resources."""
    print("\n" + "=" * 60)
    print("Cleanup")
    print("=" * 60)

    try:
        if catalog_name:
            spark.sql(f"DROP TABLE IF EXISTS {catalog_name}.{TEST_SCHEMA}.{TEST_TABLE}")
            spark.sql(f"DROP NAMESPACE IF EXISTS {catalog_name}.{TEST_SCHEMA}")
            print("  ✅ Cleaned up Spark/Iceberg resources")

        # Clean up via REST API
        if REQUESTS_AVAILABLE:
            try:
                # Delete schema (will fail if not empty, which is fine)
                requests.delete(f"{UC_API_URL}/schemas/{TEST_CATALOG}.{TEST_SCHEMA}")
            except Exception:
                pass

        print("  ✅ Cleanup completed")

    except Exception as e:
        print(f"  ⚠️  Cleanup warning: {e}")


def main():
    print("=" * 60)
    print("Unity Catalog Live Integration Test")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Unity Catalog URL: {UC_BASE_URL}")
    print("=" * 60)

    # Initialize Spark
    spark = SparkSession.builder \
        .appName("UnityCatalog-Live-Test") \
        .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    results = {}
    catalog_name = None

    # Run tests
    results['health_check'] = check_uc_health()

    if not results['health_check']:
        print("\n❌ Unity Catalog not available. Skipping remaining tests.")
        print("   Start Unity Catalog with: ./lakehouse start unity-catalog")
        sys.exit(1)

    results['rest_api'] = test_rest_api_operations()
    catalog_name = test_spark_with_uc(spark)
    results['spark_uc'] = catalog_name is not None
    results['rest_verify'] = test_table_via_rest()
    results['iceberg_metadata'] = test_iceberg_metadata(spark, catalog_name)
    results['schema_evolution'] = test_schema_evolution(spark, catalog_name)

    # Cleanup
    if '--no-cleanup' not in sys.argv:
        cleanup(spark, catalog_name)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test}: {status}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ Unity Catalog live integration test passed!")
        print("   Unity Catalog ↔ Spark ↔ Iceberg working correctly")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
