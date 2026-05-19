# Quickstart

Get the lakehouse stack running in 5 minutes.

## Prerequisites

You need these installed:
- Docker & Docker Compose v2
- Python 3.10+
- Poetry
- PostgreSQL 16 (running)
- SeaweedFS (running)

> Don't have these? See [Installation Guide](installation.md) for setup instructions.

## Setup

```bash
# Clone the repo
git clone https://github.com/lisancao/lakehouse-at-home.git
cd lakehouse-at-home

# Run automated setup
./lakehouse setup
```

The setup command will:
- Validate all prerequisites
- Download required JARs (~860MB)
- Create config files from templates
- Install Python dependencies

## Configure

Edit the generated config files with your credentials:

```bash
# Database and S3 credentials
nano .env

# Spark configuration
nano config/spark/spark-defaults.conf
```

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
