# Quickstart

Get the lakehouse stack running in 5 minutes.

## Prerequisites

You need these installed:
- Docker & Docker Compose 2.24+ (the `env_file` `required:` field needs 2.24.0)
- Python 3.10+
- Poetry
- Docker daemon running (PostgreSQL and SeaweedFS run in Compose)

> Don't have these? See [Installation Guide](installation.md) for setup instructions.

## Setup

```bash
# Clone the repo
git clone https://github.com/open-lakehouse/open-lakehouse.git
cd open-lakehouse

# Generate credentials before storage is initialized
./lakehouse setup --credentials-only
./lakehouse start storage

# Download dependencies and provision the database
./lakehouse setup
```

The setup command will:
- Validate all prerequisites
- Download required JARs (~860MB)
- Create config files from templates
- Install Python dependencies

## Configure

Setup generates private credentials and aligns Spark and Unity Catalog S3 settings.
Existing values are preserved; manual credential edits are unnecessary for a fresh
local installation. See [automatic local credentials](../guides/local-credentials.md)
for recovering an existing installation or configuring external storage.

## Start

```bash
# Start all services
./lakehouse start all

# Verify everything works
./lakehouse test
```

Expected output:
```
✓ PostgreSQL connected
✓ SeaweedFS responding
✓ Kafka broker healthy
✓ Spark master healthy
All tests passed!
```

## Verify

Open the Spark UI to confirm the cluster is running:
- **Spark 4.1 UI**: http://localhost:8082

## Next Steps

- [Generate test data](../guides/test-data.md)
- [Run streaming examples](../guides/streaming.md)
- [CLI command reference](../guides/cli-reference.md)
