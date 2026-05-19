-- Migration: v001_initial_medallion
-- Description: Create initial medallion architecture namespaces in PostgreSQL
-- Note: This prepares the JDBC catalog metadata tables for Iceberg namespaces
--       The actual Iceberg namespaces are created via Spark SQL

-- Create a table to track Iceberg namespace metadata
-- (Iceberg JDBC catalog creates its own tables, but this helps with tracking)
CREATE TABLE IF NOT EXISTS lakehouse_namespaces (
    namespace_name VARCHAR(255) PRIMARY KEY,
    namespace_type VARCHAR(50) NOT NULL, -- bronze, silver, gold, raw
    description TEXT,
    owner VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert medallion namespace metadata
INSERT INTO lakehouse_namespaces (namespace_name, namespace_type, description, owner)
VALUES
    ('bronze', 'bronze', 'Raw ingested data with minimal transformation', 'lakehouse-admin'),
    ('silver', 'silver', 'Cleaned, validated, and enriched data', 'lakehouse-admin'),
    ('gold', 'gold', 'Business-level aggregations and metrics', 'lakehouse-admin')
ON CONFLICT (namespace_name) DO NOTHING;

-- Create a table to track table lineage
CREATE TABLE IF NOT EXISTS lakehouse_lineage (
    id SERIAL PRIMARY KEY,
    source_namespace VARCHAR(255) NOT NULL,
    source_table VARCHAR(255) NOT NULL,
    target_namespace VARCHAR(255) NOT NULL,
    target_table VARCHAR(255) NOT NULL,
    transformation_type VARCHAR(50), -- etl, aggregation, join, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for lineage lookups
CREATE INDEX IF NOT EXISTS idx_lineage_source ON lakehouse_lineage(source_namespace, source_table);
CREATE INDEX IF NOT EXISTS idx_lineage_target ON lakehouse_lineage(target_namespace, target_table);

COMMENT ON TABLE lakehouse_namespaces IS 'Tracks Iceberg namespace metadata for medallion architecture';
COMMENT ON TABLE lakehouse_lineage IS 'Tracks data lineage between Iceberg tables';
