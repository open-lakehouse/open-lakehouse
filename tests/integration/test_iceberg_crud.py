"""Integration tests for Iceberg CRUD operations.

Tests basic Iceberg table operations including create, read, update, delete,
and time travel capabilities.
"""

import pytest


@pytest.mark.integration
class TestIcebergCRUD:
    """Test basic Iceberg table operations."""

    def test_create_namespace(self, spark_local):
        """Test creating Iceberg namespaces."""
        spark = spark_local

        # Create bronze namespace
        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.bronze")

        # Verify namespace exists
        namespaces = spark.sql("SHOW NAMESPACES IN iceberg").collect()
        namespace_names = [row[0] for row in namespaces]

        assert "bronze" in namespace_names

    def test_create_table(self, spark_local):
        """Test creating an Iceberg table."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_crud")

        # Create table
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_crud.orders (
                order_id STRING,
                customer_id STRING,
                amount DOUBLE,
                created_at TIMESTAMP
            )
            USING iceberg
        """)

        # Verify table exists
        tables = spark.sql("SHOW TABLES IN iceberg.test_crud").collect()
        table_names = [row.tableName for row in tables]

        assert "orders" in table_names

    def test_insert_data(self, spark_local):
        """Test inserting data into Iceberg table."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_insert")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_insert.events (
                event_id STRING,
                event_type STRING,
                payload STRING,
                ts TIMESTAMP
            )
            USING iceberg
        """)

        # Insert data
        spark.sql("""
            INSERT INTO iceberg.test_insert.events VALUES
            ('e1', 'click', '{"page": "home"}', current_timestamp()),
            ('e2', 'purchase', '{"item": "widget"}', current_timestamp()),
            ('e3', 'click', '{"page": "products"}', current_timestamp())
        """)

        # Verify data
        count = spark.sql("SELECT COUNT(*) FROM iceberg.test_insert.events").collect()[
            0
        ][0]
        assert count == 3

    def test_update_data(self, spark_local):
        """Test updating data in Iceberg table."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_update")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_update.products (
                product_id STRING,
                name STRING,
                price DOUBLE
            )
            USING iceberg
        """)

        # Insert initial data
        spark.sql("""
            INSERT INTO iceberg.test_update.products VALUES
            ('p1', 'Widget', 9.99),
            ('p2', 'Gadget', 19.99)
        """)

        # Update price
        spark.sql("""
            UPDATE iceberg.test_update.products
            SET price = 14.99
            WHERE product_id = 'p1'
        """)

        # Verify update
        result = spark.sql("""
            SELECT price FROM iceberg.test_update.products
            WHERE product_id = 'p1'
        """).collect()

        assert result[0][0] == 14.99

    def test_delete_data(self, spark_local):
        """Test deleting data from Iceberg table."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_delete")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_delete.logs (
                log_id STRING,
                level STRING,
                message STRING
            )
            USING iceberg
        """)

        # Insert data
        spark.sql("""
            INSERT INTO iceberg.test_delete.logs VALUES
            ('l1', 'INFO', 'Started'),
            ('l2', 'ERROR', 'Failed'),
            ('l3', 'INFO', 'Completed')
        """)

        # Delete ERROR logs
        spark.sql("""
            DELETE FROM iceberg.test_delete.logs
            WHERE level = 'ERROR'
        """)

        # Verify deletion
        count = spark.sql("""
            SELECT COUNT(*) FROM iceberg.test_delete.logs
            WHERE level = 'ERROR'
        """).collect()[0][0]

        assert count == 0

    def test_schema_evolution(self, spark_local):
        """Test adding columns to existing Iceberg table."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_schema")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_schema.users (
                user_id STRING,
                name STRING
            )
            USING iceberg
        """)

        # Add new column
        spark.sql("""
            ALTER TABLE iceberg.test_schema.users
            ADD COLUMN email STRING
        """)

        # Insert with new column
        spark.sql("""
            INSERT INTO iceberg.test_schema.users VALUES
            ('u1', 'Alice', 'alice@example.com')
        """)

        # Verify new column works
        result = spark.sql("""
            SELECT email FROM iceberg.test_schema.users
            WHERE user_id = 'u1'
        """).collect()

        assert result[0][0] == "alice@example.com"

    @pytest.mark.slow
    def test_time_travel(self, spark_local):
        """Test Iceberg time travel capabilities."""
        spark = spark_local

        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.test_timetravel")
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.test_timetravel.metrics (
                metric_name STRING,
                value DOUBLE
            )
            USING iceberg
        """)

        # Insert initial data
        spark.sql("""
            INSERT INTO iceberg.test_timetravel.metrics VALUES
            ('cpu', 50.0)
        """)

        # Get snapshot ID after first insert
        snapshots = spark.sql("""
            SELECT snapshot_id FROM iceberg.test_timetravel.metrics.snapshots
            ORDER BY committed_at ASC
        """).collect()
        first_snapshot = snapshots[0][0]

        # Update data
        spark.sql("""
            UPDATE iceberg.test_timetravel.metrics
            SET value = 75.0
            WHERE metric_name = 'cpu'
        """)

        # Verify current value
        current = spark.sql("""
            SELECT value FROM iceberg.test_timetravel.metrics
            WHERE metric_name = 'cpu'
        """).collect()[0][0]
        assert current == 75.0

        # Time travel to first snapshot
        historical = spark.sql(f"""
            SELECT value FROM iceberg.test_timetravel.metrics
            VERSION AS OF {first_snapshot}
            WHERE metric_name = 'cpu'
        """).collect()[0][0]
        assert historical == 50.0


@pytest.mark.integration
class TestMedallionArchitecture:
    """Test medallion architecture namespace operations."""

    def test_create_medallion_namespaces(self, spark_local):
        """Test creating bronze/silver/gold namespaces."""
        spark = spark_local

        # Create medallion namespaces
        for namespace in ["bronze", "silver", "gold"]:
            spark.sql(f"CREATE NAMESPACE IF NOT EXISTS iceberg.{namespace}")

        # Verify all exist
        namespaces = spark.sql("SHOW NAMESPACES IN iceberg").collect()
        namespace_names = [row[0] for row in namespaces]

        assert "bronze" in namespace_names
        assert "silver" in namespace_names
        assert "gold" in namespace_names

    def test_medallion_data_flow(self, spark_local):
        """Test data flowing through bronze -> silver -> gold."""
        spark = spark_local

        # Setup namespaces
        for ns in ["bronze", "silver", "gold"]:
            spark.sql(f"CREATE NAMESPACE IF NOT EXISTS iceberg.medallion_{ns}")

        # Bronze: Raw events
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.medallion_bronze.raw_events (
                event_id STRING,
                event_type STRING,
                raw_data STRING,
                ingested_at TIMESTAMP
            )
            USING iceberg
        """)

        spark.sql("""
            INSERT INTO iceberg.medallion_bronze.raw_events VALUES
            ('e1', 'order', '{"order_id": "o1", "amount": 100}', current_timestamp()),
            ('e2', 'order', '{"order_id": "o2", "amount": 200}', current_timestamp()),
            ('e3', 'click', '{"page": "home"}', current_timestamp())
        """)

        # Silver: Cleaned/parsed orders
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.medallion_silver.orders (
                order_id STRING,
                amount DOUBLE,
                processed_at TIMESTAMP
            )
            USING iceberg
        """)

        # Transform bronze to silver (filter orders, parse JSON)
        spark.sql("""
            INSERT INTO iceberg.medallion_silver.orders
            SELECT
                get_json_object(raw_data, '$.order_id') as order_id,
                CAST(get_json_object(raw_data, '$.amount') AS DOUBLE) as amount,
                current_timestamp() as processed_at
            FROM iceberg.medallion_bronze.raw_events
            WHERE event_type = 'order'
        """)

        # Gold: Aggregations
        spark.sql("""
            CREATE TABLE IF NOT EXISTS iceberg.medallion_gold.order_summary (
                total_orders BIGINT,
                total_amount DOUBLE,
                avg_amount DOUBLE,
                computed_at TIMESTAMP
            )
            USING iceberg
        """)

        spark.sql("""
            INSERT INTO iceberg.medallion_gold.order_summary
            SELECT
                COUNT(*) as total_orders,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount,
                current_timestamp() as computed_at
            FROM iceberg.medallion_silver.orders
        """)

        # Verify gold layer
        result = spark.sql("""
            SELECT total_orders, total_amount FROM iceberg.medallion_gold.order_summary
        """).collect()[0]

        assert result.total_orders == 2
        assert result.total_amount == 300.0
