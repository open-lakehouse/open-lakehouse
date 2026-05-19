# Local Deployment

This guide covers running the lakehouse stack on your local machine for development and testing.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Host Machine                          │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ PostgreSQL   │  │  SeaweedFS   │  │    Docker    │  │
│  │   (native)   │  │   (native)   │  │              │  │
│  │  port 5432   │  │  port 8333   │  │ ┌──────────┐ │  │
│  └──────────────┘  └──────────────┘  │ │  Spark   │ │  │
│                                       │ │  Master  │ │  │
│                                       │ ├──────────┤ │  │
│                                       │ │  Spark   │ │  │
│                                       │ │  Worker  │ │  │
│                                       │ ├──────────┤ │  │
│                                       │ │  Kafka   │ │  │
│                                       │ ├──────────┤ │  │
│                                       │ │Zookeeper │ │  │
│                                       │ ├──────────┤ │  │
│                                       │ │ Airflow  │ │  │
│                                       │ │(optional)│ │  │
│                                       │ └──────────┘ │  │
│                                       └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

See [Installation Guide](../getting-started/installation.md) for setup.

Required:
- Docker & Docker Compose v2
- PostgreSQL 16 (running natively)
- SeaweedFS (running natively)
- Python 3.10+ with Poetry

## Starting Services

```bash
# Start everything
./lakehouse start all

# Or start components individually
./lakehouse start spark
./lakehouse start kafka
```

## Service Ports

| Service | Port | UI |
|---------|------|-----|
| PostgreSQL | 5432 | - |
| SeaweedFS | 8333 | - |
| Spark 4.1 Master | 7078 | http://localhost:8082 |
| Kafka | 9092 | - |
| Zookeeper | 2181 | - |
| Unity Catalog | 8081 | REST API |
| MLflow Tracking | 5000 | http://localhost:5000 |
| MLflow AI Gateway | 5001 | - |
| Airflow (optional) | 8085 | http://localhost:8085 |

## Running Spark Jobs

### Via Docker (recommended)

```bash
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --master spark://localhost:7078 \
  /scripts/<your-job>.py
```

Scripts directory is mounted at `/scripts/` inside the container.

### Local spark-submit (host)

Requires Java 21 (matches Spark 4.1):

```bash
spark-submit \
  --master spark://localhost:7078 \
  --jars jars/iceberg-spark-runtime-4.0_2.13-1.10.0.jar \
  scripts/<your-job>.py
```

(The JAR is named `4.0` upstream — it's Iceberg 1.10's Spark 4.0+ runtime, which works with Spark 4.1.)

## Resource Management

### Checking Resources

```bash
# Docker stats
docker stats spark-master-41 spark-worker-41 kafka zookeeper

# Disk usage
du -sh jars/ data/
```

### Cleanup

```bash
# Stop all services
./lakehouse stop all

# Remove generated data
./lakehouse testdata clean

# Docker cleanup
docker system prune -f
```

## Data Persistence

| Data | Location | Persisted |
|------|----------|-----------|
| Iceberg metadata | PostgreSQL | Yes |
| Table data | SeaweedFS | Yes |
| Kafka topics | Docker volume | Until container removed |
| Spark logs | Docker container | Until container removed |

## Networking

The stack uses `network_mode: host`:
- All containers share host network
- No port mapping needed
- `localhost` works everywhere

This means:
- Simpler configuration
- No Docker network isolation
- Ports must not conflict with host services

## Troubleshooting

See [Troubleshooting Guide](../troubleshooting.md) for common issues.

Quick checks:
```bash
# Service health
./lakehouse test

# JSON status for scripting
./lakehouse status --json

# View logs
./lakehouse logs spark-master
./lakehouse logs kafka
```

## Next Steps

- [Test Data Generation](../guides/test-data.md)
- [Streaming Guide](../guides/streaming.md)
- [Airflow Orchestration](../guides/airflow.md)
- [AWS Deployment](aws.md) - For production
