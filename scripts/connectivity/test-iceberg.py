from pyspark.sql import SparkSession

print("=" * 60)
print("Testing Iceberg Catalog Connection")
print("=" * 60)

# SparkSession is already created by spark-submit
spark = SparkSession.builder.getOrCreate()

try:
    # Create namespaces if they don't exist
    spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.bronze")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.silver")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.gold")

    # 1. List namespaces
    print("\n1. Listing namespaces:")
    spark.sql("SHOW NAMESPACES IN iceberg").show()

    # 2. List tables in bronze
    print("\n2. Listing tables in bronze namespace:")
    spark.sql("SHOW TABLES IN iceberg.bronze").show()

    # 3. Create a new Spark test table
    print("\n3. Creating new spark_test table:")
    spark.sql("""
        CREATE TABLE IF NOT EXISTS iceberg.bronze.spark_test (
            id INT,
            name STRING,
            value DOUBLE,
            timestamp TIMESTAMP
        ) USING iceberg
    """)
    print("✅ Table created successfully!")

    # 4. Insert test data
    print("\n4. Inserting test data:")
    spark.sql("""
        INSERT INTO iceberg.bronze.spark_test VALUES
        (1, 'test1', 100.5, current_timestamp()),
        (2, 'test2', 200.7, current_timestamp()),
        (3, 'test3', 300.9, current_timestamp())
    """)
    print("✅ Data inserted!")

    # 5. Read data back
    print("\n5. Reading data from spark_test:")
    spark.sql("SELECT * FROM iceberg.bronze.spark_test").show()

    # 6. Show table metadata
    print("\n6. Table metadata:")
    spark.sql("DESCRIBE EXTENDED iceberg.bronze.spark_test").show(truncate=False)

    print("\n✅ All tests completed successfully!")

except Exception as e:
    print(f"\nError: {e}")
    import traceback
