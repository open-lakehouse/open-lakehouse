#!/usr/bin/env bash
# Teardown for the realtime-mode RTM demo. Idempotent.
set -euo pipefail

DEMO_NAME="realtime-mode"
echo "→ teardown: ${DEMO_NAME}"

# Stop the streaming spark-submit running inside the Spark master container.
# pkill returns 1 if nothing matched; tolerate that with `|| true`.
docker exec spark-master-41 \
  pkill -f "rtm_pipeline.py" || true

# Delete demo Kafka topics.
for t in ethereum-blocks ethereum-validated-allowed ethereum-validated-quarantine; do
  docker exec kafka kafka-topics --delete --if-exists \
    --topic "$t" --bootstrap-server localhost:9092 || true
done

# Remove the checkpoint directory on the Spark master volume.
docker exec spark-master-41 \
  rm -rf /opt/spark-data/checkpoints/rtm-realtime-mode || true

echo "✓ teardown: ${DEMO_NAME} complete"
