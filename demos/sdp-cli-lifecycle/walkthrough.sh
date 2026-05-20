#!/usr/bin/env bash
# SDP project lifecycle as shell commands — init → inspect → dry-run → edit → run.
#
# Every step is a `spark-pipelines` invocation (or an edit to what it
# scaffolded). Runs the example project that `init` generates — a Python
# materialized view + a SQL one — against spark_catalog.default. No Unity
# Catalog, no Kafka, no test data.
#
# Usage:  bash demos/sdp-cli-lifecycle/walkthrough.sh
set -euo pipefail

C=spark-master-41
PROJ=/tmp/sdp-lifecycle
SP="PYTHONPATH=/tmp/pylibs:\$PYTHONPATH /opt/spark/bin/spark-pipelines"

step() { printf '\n\033[1;34m── %s\033[0m\n' "$1"; }

# spark-pipelines embeds its own Connect server on 15002 — free the port.
step "0. stop the standalone Connect server (port 15002 collision)"
docker stop spark-connect-41 >/dev/null 2>&1 || true

step "1. spark-pipelines init — scaffold a project"
docker exec -u root "$C" sh -c "rm -rf $PROJ && mkdir -p $PROJ && cd $PROJ && $SP init --name app 2>&1 | grep -v WARN | tail -3"

step "2. project structure that init generated"
docker exec "$C" find "$PROJ/app" -type f
echo "--- spark-pipeline.yml ---"
docker exec "$C" cat "$PROJ/app/spark-pipeline.yml"

step "3. spark-pipelines dry-run — validate the dataflow graph, write nothing"
docker exec -u root "$C" sh -c "cd $PROJ/app && $SP dry-run 2>&1 | grep -vE 'WARN|SLF4J' | tail -6"

step "4. edit the transformations, then dry-run again"
echo "(the inner dev loop: edit a transformation, dry-run, repeat — dry-run"
echo " materializes nothing, so it is always safe to re-run)"
# Give the example datasets project-specific names. This is a real edit; it
# also gives the run below fresh storage paths (see README "Notes").
docker exec -u root "$C" sh -c \
  "cd $PROJ/app/transformations && sed -i \
   's/example_python_materialized_view/clife_nums/g; s/example_sql_materialized_view/clife_even/g' \
   *.py *.sql"
docker exec -u root "$C" sh -c "cd $PROJ/app && $SP dry-run 2>&1 | grep -vE 'WARN|SLF4J' | tail -3"

step "5. spark-pipelines run — execute the pipeline, materialize the datasets"
docker exec -u root "$C" sh -c "cd $PROJ/app && $SP run 2>&1 | grep -E 'Flow .* COMPLETED|Run is' | tail -6"

step "done — restarting the standalone Connect server"
docker start spark-connect-41 >/dev/null 2>&1 || true
echo "✓ lifecycle walkthrough complete"
echo
echo "To run the pipeline again, tear down first (see teardown.sh) — SDP"
echo "materializes with a fresh CREATE TABLE and will not overwrite the"
echo "previous run's data. --full-refresh-all is the documented reset; see README."
