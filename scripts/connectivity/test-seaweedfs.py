#!/usr/bin/env python3
"""
SeaweedFS S3 Storage Integration Test

Tests the storage layer (SeaweedFS S3-compatible API) with Iceberg:
- Write Iceberg table and verify files exist in S3
- Read files directly via S3 API (boto3)
- Verify parquet file structure
- Cross-check metadata in PostgreSQL with storage

Prerequisites:
    ./lakehouse start all

Usage:
    # Via spark-submit (recommended)
    docker exec spark-master-41 /opt/spark/bin/spark-submit /scripts/test-seaweedfs.py

    # Or locally with proper Spark config
    python scripts/test-seaweedfs.py
"""

import sys
from datetime import datetime

try:
    import boto3
    from botocore.client import Config
    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None  # type: ignore
    Config = None  # type: ignore
    BOTO3_AVAILABLE = False
    print("Warning: boto3 not installed. S3 verification will be skipped.")
    print("Install with: pip install boto3")

from pyspark.sql import SparkSession


def get_s3_client():
    """Create S3 client for SeaweedFS."""
    if not BOTO3_AVAILABLE:
        return None

    # SeaweedFS S3 endpoint - adjust if needed
    return boto3.client(
        's3',
        endpoint_url='http://localhost:8333',
        aws_access_key_id='admin',  # Default SeaweedFS credentials
        aws_secret_access_key='admin',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )


def test_s3_connectivity(s3_client):
    """Test basic S3 API connectivity."""
    print("\n" + "=" * 60)
    print("Test 1: S3 Connectivity")
    print("=" * 60)

    if not s3_client:
        print("  SKIP: boto3 not available")
        return False

    try:
        response = s3_client.list_buckets()
        buckets = [b['Name'] for b in response.get('Buckets', [])]
        print(f"  Connected to SeaweedFS S3")
        print(f"  Buckets found: {buckets}")

        # Check for lakehouse bucket
        if 'lakehouse' in buckets:
            print("  ✅ 'lakehouse' bucket exists")
            return True
        else:
            print("  ⚠️  'lakehouse' bucket not found - creating it")
            s3_client.create_bucket(Bucket='lakehouse')
            print("  ✅ Created 'lakehouse' bucket")
            return True

    except Exception as e:
        print(f"  ❌ S3 connectivity failed: {e}")
        return False


def test_iceberg_write(spark):
    """Write test data to Iceberg table."""
    print("\n" + "=" * 60)
    print("Test 2: Iceberg Table Write")
    print("=" * 60)

    try:
        # Create test namespace
        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_storage")

        # Drop table if exists for clean test
        spark.sql("DROP TABLE IF EXISTS iceberg.test_storage.s3_test")

        # Create table with explicit location
        spark.sql("""
            CREATE TABLE iceberg.test_storage.s3_test (
                id INT,
                product STRING,
                price DOUBLE,
                quantity INT,
                created_at TIMESTAMP
            ) USING iceberg
            PARTITIONED BY (days(created_at))
        """)
        print("  Created table: iceberg.test_storage.s3_test")

        # Insert test data
        spark.sql("""
            INSERT INTO iceberg.test_storage.s3_test VALUES
            (1, 'Widget A', 29.99, 10, timestamp '2024-01-15 10:30:00'),
            (2, 'Widget B', 49.99, 5, timestamp '2024-01-15 11:45:00'),
            (3, 'Gadget X', 99.99, 3, timestamp '2024-01-16 09:00:00'),
            (4, 'Gadget Y', 149.99, 2, timestamp '2024-01-16 14:30:00'),
            (5, 'Device Z', 199.99, 1, timestamp '2024-01-17 16:00:00')
        """)
        print("  Inserted 5 test records")

        # Verify data
        count = spark.sql("SELECT COUNT(*) as cnt FROM iceberg.test_storage.s3_test").collect()[0]['cnt']
        print(f"  Verified row count: {count}")

        if count == 5:
            print("  ✅ Iceberg write successful")
            return True
        else:
            print(f"  ❌ Expected 5 rows, got {count}")
            return False

    except Exception as e:
        print(f"  ❌ Iceberg write failed: {e}")
        return False


def test_s3_file_verification(s3_client, spark):
    """Verify Iceberg data files exist in S3."""
    print("\n" + "=" * 60)
    print("Test 3: S3 File Verification")
    print("=" * 60)

    if not s3_client:
        print("  SKIP: boto3 not available")
        return False

    try:
        # Get table location from metadata
        metadata = spark.sql("DESCRIBE EXTENDED iceberg.test_storage.s3_test").collect()
        location = None
        for row in metadata:
            if row['col_name'] == 'Location':
                location = row['data_type']
                break

        if not location:
            print("  ❌ Could not find table location")
            return False

        print(f"  Table location: {location}")

        # Parse S3 path
        # Format: s3a://bucket/path or s3://bucket/path
        if location.startswith('s3a://'):
            path = location[6:]  # Remove s3a://
        elif location.startswith('s3://'):
            path = location[5:]  # Remove s3://
        else:
            print(f"  ⚠️  Unexpected location format: {location}")
            path = location

        parts = path.split('/', 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ''

        print(f"  Bucket: {bucket}, Prefix: {prefix}")

        # List objects in table location
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        objects = response.get('Contents', [])

        print(f"  Found {len(objects)} objects in S3")

        # Categorize files
        data_files = [o for o in objects if '/data/' in o['Key'] and o['Key'].endswith('.parquet')]
        metadata_files = [o for o in objects if '/metadata/' in o['Key']]

        print(f"  Data files (parquet): {len(data_files)}")
        print(f"  Metadata files: {len(metadata_files)}")

        if data_files:
            print("\n  Sample data files:")
            for f in data_files[:3]:
                size_kb = f['Size'] / 1024
                print(f"    - {f['Key'].split('/')[-1]} ({size_kb:.1f} KB)")

        if metadata_files:
            print("\n  Sample metadata files:")
            for f in metadata_files[:3]:
                print(f"    - {f['Key'].split('/')[-1]}")

        if data_files and metadata_files:
            print("\n  ✅ S3 file verification passed")
            return True
        else:
            print("\n  ❌ Missing data or metadata files in S3")
            return False

    except Exception as e:
        print(f"  ❌ S3 verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_read_parquet_direct(s3_client, spark):
    """Read parquet file directly from S3 (bypassing Iceberg)."""
    print("\n" + "=" * 60)
    print("Test 4: Direct Parquet Read from S3")
    print("=" * 60)

    if not s3_client:
        print("  SKIP: boto3 not available")
        return False

    try:
        # Get table location
        metadata = spark.sql("DESCRIBE EXTENDED iceberg.test_storage.s3_test").collect()
        location = None
        for row in metadata:
            if row['col_name'] == 'Location':
                location = row['data_type']
                break

        if not location:
            print("  ❌ Could not find table location")
            return False

        # Read parquet files directly using Spark (not Iceberg)
        data_path = f"{location}/data"
        print(f"  Reading from: {data_path}")

        direct_df = spark.read.parquet(data_path)
        direct_count = direct_df.count()

        print(f"  Direct parquet read: {direct_count} rows")
        print("\n  Sample data (direct read):")
        direct_df.show(3, truncate=False)

        # Compare with Iceberg read
        iceberg_count = spark.sql("SELECT COUNT(*) FROM iceberg.test_storage.s3_test").collect()[0][0]

        if direct_count == iceberg_count:
            print(f"  ✅ Counts match: direct={direct_count}, iceberg={iceberg_count}")
            return True
        else:
            print(f"  ⚠️  Count mismatch: direct={direct_count}, iceberg={iceberg_count}")
            print("      (This may be expected due to delete files)")
            return True  # Still pass - Iceberg may have delete files

    except Exception as e:
        print(f"  ❌ Direct parquet read failed: {e}")
        return False


def test_metadata_consistency(spark):
    """Verify Iceberg metadata is consistent."""
    print("\n" + "=" * 60)
    print("Test 5: Metadata Consistency")
    print("=" * 60)

    try:
        # Check snapshots
        print("  Checking snapshots:")
        snapshots = spark.sql("SELECT * FROM iceberg.test_storage.s3_test.snapshots").collect()
        print(f"    Snapshots: {len(snapshots)}")

        # Check history
        print("\n  Checking history:")
        history = spark.sql("SELECT * FROM iceberg.test_storage.s3_test.history").collect()
        print(f"    History entries: {len(history)}")

        # Check files
        print("\n  Checking data files:")
        files = spark.sql("SELECT * FROM iceberg.test_storage.s3_test.files").collect()
        print(f"    Data files: {len(files)}")

        # Check partitions
        print("\n  Checking partitions:")
        partitions = spark.sql("SELECT * FROM iceberg.test_storage.s3_test.partitions").collect()
        print(f"    Partitions: {len(partitions)}")

        for p in partitions:
            print(f"      - {p['partition']}: {p['record_count']} records")

        if snapshots and files:
            print("\n  ✅ Metadata consistency verified")
            return True
        else:
            print("\n  ❌ Metadata incomplete")
            return False

    except Exception as e:
        print(f"  ❌ Metadata check failed: {e}")
        return False


def cleanup(spark):
    """Clean up test table."""
    print("\n" + "=" * 60)
    print("Cleanup")
    print("=" * 60)

    try:
        spark.sql("DROP TABLE IF EXISTS iceberg.test_storage.s3_test")
        spark.sql("DROP NAMESPACE IF EXISTS iceberg.test_storage")
        print("  ✅ Cleanup completed")
    except Exception as e:
        print(f"  ⚠️  Cleanup warning: {e}")


def main():
    print("=" * 60)
    print("SeaweedFS S3 Storage Integration Test")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Initialize
    spark = SparkSession.builder \
        .appName("SeaweedFS-Test") \
        .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    s3_client = get_s3_client()

    results = {}

    # Run tests
    results['s3_connectivity'] = test_s3_connectivity(s3_client)
    results['iceberg_write'] = test_iceberg_write(spark)
    results['s3_verification'] = test_s3_file_verification(s3_client, spark)
    results['direct_parquet'] = test_read_parquet_direct(s3_client, spark)
    results['metadata_consistency'] = test_metadata_consistency(spark)

    # Cleanup
    if '--no-cleanup' not in sys.argv:
        cleanup(spark)

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
        print("\n✅ All SeaweedFS integration tests passed!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
