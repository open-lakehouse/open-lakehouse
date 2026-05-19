-- Migration: v001_initial_catalogs
-- Description: Prepare metadata tracking for Unity Catalog OSS integration
-- Note: Unity Catalog has its own backend, this tracks integration metadata

-- Track Unity Catalog integration status
CREATE TABLE IF NOT EXISTS unity_catalog_sync (
    id SERIAL PRIMARY KEY,
    iceberg_namespace VARCHAR(255) NOT NULL,
    iceberg_table VARCHAR(255) NOT NULL,
    unity_catalog VARCHAR(255) NOT NULL,
    unity_schema VARCHAR(255) NOT NULL,
    unity_table VARCHAR(255) NOT NULL,
    sync_status VARCHAR(50) DEFAULT 'pending', -- pending, synced, failed, disabled
    last_sync_at TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(iceberg_namespace, iceberg_table, unity_catalog)
);

-- Track Unity Catalog credentials (encrypted references only)
CREATE TABLE IF NOT EXISTS unity_catalog_connections (
    id SERIAL PRIMARY KEY,
    connection_name VARCHAR(255) UNIQUE NOT NULL,
    catalog_endpoint VARCHAR(500) NOT NULL,
    catalog_name VARCHAR(255) NOT NULL,
    auth_type VARCHAR(50) NOT NULL, -- token, oauth, service_account
    credential_secret_name VARCHAR(255), -- Reference to secret manager
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_unity_sync_status ON unity_catalog_sync(sync_status);
CREATE INDEX IF NOT EXISTS idx_unity_sync_iceberg ON unity_catalog_sync(iceberg_namespace, iceberg_table);

-- Insert default connection placeholder
INSERT INTO unity_catalog_connections
    (connection_name, catalog_endpoint, catalog_name, auth_type, is_active)
VALUES
    ('local-unity', 'http://localhost:8080/api/2.1/unity-catalog', 'unity', 'token', false)
ON CONFLICT (connection_name) DO NOTHING;

COMMENT ON TABLE unity_catalog_sync IS 'Tracks synchronization between Iceberg and Unity Catalog tables';
COMMENT ON TABLE unity_catalog_connections IS 'Unity Catalog connection configurations (credentials stored externally)';
