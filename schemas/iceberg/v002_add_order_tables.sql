-- Migration: v002_add_order_tables
-- Description: Register order-related table metadata
-- Note: Actual Iceberg tables are created via Spark SQL
--       This tracks metadata for operational purposes

-- Track expected tables in each namespace
CREATE TABLE IF NOT EXISTS lakehouse_table_registry (
    id SERIAL PRIMARY KEY,
    namespace_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    table_type VARCHAR(50) NOT NULL, -- fact, dimension, aggregate, staging
    description TEXT,
    partition_spec TEXT, -- JSON description of partitioning
    expected_schema TEXT, -- JSON schema definition
    sla_freshness_hours INTEGER, -- Expected data freshness SLA
    owner VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(namespace_name, table_name)
);

-- Register bronze layer tables
INSERT INTO lakehouse_table_registry
    (namespace_name, table_name, table_type, description, partition_spec, sla_freshness_hours)
VALUES
    ('bronze', 'raw_orders', 'staging', 'Raw order events from Kafka',
     '{"type": "hour", "column": "event_timestamp"}', 1),
    ('bronze', 'raw_clicks', 'staging', 'Raw clickstream events',
     '{"type": "hour", "column": "event_timestamp"}', 1),
    ('bronze', 'raw_inventory', 'staging', 'Raw inventory updates',
     '{"type": "day", "column": "updated_at"}', 24)
ON CONFLICT (namespace_name, table_name) DO NOTHING;

-- Register silver layer tables
INSERT INTO lakehouse_table_registry
    (namespace_name, table_name, table_type, description, partition_spec, sla_freshness_hours)
VALUES
    ('silver', 'orders', 'fact', 'Cleaned and validated orders',
     '{"type": "day", "column": "order_date"}', 2),
    ('silver', 'order_items', 'fact', 'Order line items with product details',
     '{"type": "day", "column": "order_date"}', 2),
    ('silver', 'customers', 'dimension', 'Customer master data',
     NULL, 24),
    ('silver', 'products', 'dimension', 'Product catalog',
     NULL, 24)
ON CONFLICT (namespace_name, table_name) DO NOTHING;

-- Register gold layer tables
INSERT INTO lakehouse_table_registry
    (namespace_name, table_name, table_type, description, partition_spec, sla_freshness_hours)
VALUES
    ('gold', 'daily_sales', 'aggregate', 'Daily sales aggregations by region',
     '{"type": "day", "column": "sales_date"}', 4),
    ('gold', 'customer_lifetime_value', 'aggregate', 'Customer LTV metrics',
     NULL, 24),
    ('gold', 'product_performance', 'aggregate', 'Product sales performance metrics',
     '{"type": "month", "column": "period_start"}', 24)
ON CONFLICT (namespace_name, table_name) DO NOTHING;

-- Register lineage relationships
INSERT INTO lakehouse_lineage
    (source_namespace, source_table, target_namespace, target_table, transformation_type)
VALUES
    ('bronze', 'raw_orders', 'silver', 'orders', 'etl'),
    ('bronze', 'raw_orders', 'silver', 'order_items', 'etl'),
    ('silver', 'orders', 'gold', 'daily_sales', 'aggregation'),
    ('silver', 'orders', 'gold', 'customer_lifetime_value', 'aggregation'),
    ('silver', 'order_items', 'gold', 'product_performance', 'aggregation')
ON CONFLICT DO NOTHING;

-- Create index for table registry lookups
CREATE INDEX IF NOT EXISTS idx_table_registry_namespace ON lakehouse_table_registry(namespace_name);

COMMENT ON TABLE lakehouse_table_registry IS 'Registry of expected Iceberg tables with metadata';
