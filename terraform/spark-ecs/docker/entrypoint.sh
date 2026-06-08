#!/usr/bin/env bash
# entrypoint.sh — start a Spark 4.1 standalone role (master | worker | connect)
# on ECS Fargate, wired to Cloud Map service discovery.
#
# Fargate gives every task its own ENI/IP, so the JVM must advertise that exact
# address (SPARK_LOCAL_IP) or master<->worker RPC silently fails. We read it from
# the ECS task metadata endpoint. The master is reachable by workers and the
# Connect server at its Cloud Map name (SPARK_MASTER_HOST, e.g. master.spark.local).
#
# Env (set by the ECS task definition):
#   SPARK_ROLE              master | worker | connect           (required)
#   SPARK_MASTER_HOST       Cloud Map FQDN of the master        (default master.spark.local)
#   SPARK_MASTER_PORT       master RPC port                     (default 7077)
#   SPARK_MASTER_WEBUI_PORT master UI port                      (default 8080)
#   SPARK_WORKER_WEBUI_PORT worker UI port                      (default 8081)
#   SPARK_CONNECT_PORT      Connect gRPC port                   (default 15002)
#   SPARK_REVERSE_PROXY_URL public master URL for UI reverse proxy (optional)
#   SPARK_EXTRA_CONF        ';'-separated k=v pairs appended to spark-defaults  (optional)
set -euo pipefail

SPARK_HOME="${SPARK_HOME:-/opt/spark}"
ROLE="${SPARK_ROLE:?SPARK_ROLE must be set (master|worker|connect)}"
MASTER_HOST="${SPARK_MASTER_HOST:-master.spark.local}"
MASTER_PORT="${SPARK_MASTER_PORT:-7077}"
MASTER_WEBUI_PORT="${SPARK_MASTER_WEBUI_PORT:-8080}"
WORKER_WEBUI_PORT="${SPARK_WORKER_WEBUI_PORT:-8081}"
CONNECT_PORT="${SPARK_CONNECT_PORT:-15002}"
CONF_FILE="${SPARK_HOME}/conf/spark-defaults.conf"

# Keep Spark daemons in the foreground so they own PID 1 and forward signals.
export SPARK_NO_DAEMONIZE=1

# ----- Resolve this task's own IP from the ECS metadata endpoint -------------
resolve_task_ip() {
  local meta="${ECS_CONTAINER_METADATA_URI_V4:-}"
  if [[ -n "$meta" ]]; then
    local ip
    ip="$(curl -fsS "${meta}/task" 2>/dev/null \
      | grep -oE '"IPv4Addresses":\[[^]]*' \
      | grep -oE '[0-9]{1,3}(\.[0-9]{1,3}){3}' | head -1 || true)"
    [[ -n "$ip" ]] && { echo "$ip"; return 0; }
  fi
  # Fallback: first non-loopback address.
  hostname -i 2>/dev/null | tr ' ' '\n' | grep -vE '^127\.' | head -1
}

TASK_IP="$(resolve_task_ip || true)"
if [[ -n "${TASK_IP:-}" ]]; then
  export SPARK_LOCAL_IP="$TASK_IP"
  export SPARK_PUBLIC_DNS="$TASK_IP"
  echo "entrypoint: resolved task IP ${TASK_IP} (SPARK_LOCAL_IP)"
else
  echo "entrypoint: WARNING could not resolve task IP; relying on Spark defaults" >&2
fi

# ----- Layer runtime config onto the baked spark-defaults.conf ---------------
# Applies uniformly to master, worker, and connect (all read spark-defaults).
append_conf() {
  printf '%s %s\n' "$1" "$2" >> "$CONF_FILE"
}

if [[ -n "${SPARK_REVERSE_PROXY_URL:-}" ]]; then
  append_conf spark.ui.reverseProxyUrl "$SPARK_REVERSE_PROXY_URL"
fi

if [[ -n "${SPARK_EXTRA_CONF:-}" ]]; then
  IFS=';' read -ra _pairs <<< "$SPARK_EXTRA_CONF"
  for pair in "${_pairs[@]}"; do
    [[ -z "$pair" ]] && continue
    key="${pair%%=*}"
    val="${pair#*=}"
    [[ -n "$key" && "$key" != "$pair" ]] && append_conf "$key" "$val"
  done
fi

# ----- Dispatch --------------------------------------------------------------
case "$ROLE" in
  master)
    # The standalone master binds AND advertises its --host, so it must be this
    # task's own ENI IP (not the Cloud Map name, which doesn't resolve until the
    # task is registered — and can't be bound to anyway). Cloud Map maps
    # ${MASTER_HOST} -> this IP so workers/Connect reach it by name.
    BIND_IP="${SPARK_LOCAL_IP:?master requires a resolvable task IP from ECS metadata}"
    echo "entrypoint: starting Spark master, binding ${BIND_IP}:${MASTER_PORT} (advertised as ${MASTER_HOST}, UI ${MASTER_WEBUI_PORT})"
    exec "${SPARK_HOME}/bin/spark-class" org.apache.spark.deploy.master.Master \
      --host "$BIND_IP" \
      --port "$MASTER_PORT" \
      --webui-port "$MASTER_WEBUI_PORT"
    ;;
  worker)
    echo "entrypoint: starting Spark worker -> spark://${MASTER_HOST}:${MASTER_PORT} (UI ${WORKER_WEBUI_PORT})"
    exec "${SPARK_HOME}/bin/spark-class" org.apache.spark.deploy.worker.Worker \
      "spark://${MASTER_HOST}:${MASTER_PORT}" \
      --webui-port "$WORKER_WEBUI_PORT"
    ;;
  connect)
    echo "entrypoint: starting Spark Connect server -> spark://${MASTER_HOST}:${MASTER_PORT} (gRPC ${CONNECT_PORT})"
    exec "${SPARK_HOME}/sbin/start-connect-server.sh" \
      --master "spark://${MASTER_HOST}:${MASTER_PORT}" \
      --conf "spark.connect.grpc.binding.host=0.0.0.0" \
      --conf "spark.connect.grpc.binding.port=${CONNECT_PORT}"
    ;;
  *)
    echo "entrypoint: ERROR unknown SPARK_ROLE='${ROLE}' (expected master|worker|connect)" >&2
    exit 1
    ;;
esac
