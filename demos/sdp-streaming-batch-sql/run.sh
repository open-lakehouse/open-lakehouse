#!/usr/bin/env bash
# Run the streaming + batch SQL pipeline once.
#
# Run once per teardown: SDP materializes each dataset with a fresh
# CREATE TABLE, so a second run without `teardown.sh` in between fails with
# DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION. See README "Notes".
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C=spark-master-41
PROJ=/tmp/sdp-streaming-batch-sql

# spark-pipelines embeds its own Connect server on 15002 — free the port.
echo "→ stopping the standalone Connect server (port 15002)"
docker stop spark-connect-41 >/dev/null 2>&1 || true

echo "→ copying pipeline into $C"
docker exec -u root "$C" rm -rf "$PROJ"
docker cp "$DIR" "$C:$PROJ"

echo "→ seeding the source Delta table (file:///tmp/sxb-seed)"
docker exec -u root "$C" rm -rf /tmp/sxb-seed
docker exec -u root "$C" /opt/spark/bin/spark-submit --master 'local[2]' \
  "$PROJ/seed.py" >/dev/null 2>&1

echo "→ spark-pipelines run"
docker exec -u root "$C" sh -c \
  "cd $PROJ && PYTHONPATH=/tmp/pylibs:\$PYTHONPATH /opt/spark/bin/spark-pipelines run"

docker start spark-connect-41 >/dev/null 2>&1 || true
echo "✓ run complete — see expected output in README.md"
