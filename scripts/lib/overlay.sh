# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Test-only overlay resolution + destructive-target validation.
#
# This library is the single source of truth for how ./lakehouse resolves
# compose files, container names, and published ports, and for validating that
# a destructive operation running under the test overlay only touches
# run-scoped resources. It is sourced by ./lakehouse and, directly, by the
# pytest suite.
#
# It performs NO destructive actions and prints nothing when sourced.
#
# Overlay activation contract (implementation plan 1.16.1 — normative):
#   Required : LAKEHOUSE_TEST_RUN_ID, LAKEHOUSE_OVERLAY_DIR, LAKEHOUSE_RESOURCE_SUFFIX
#   Optional : LAKEHOUSE_PORT_OFFSET, LAKEHOUSE_ENV_FILE
#   Run-id   : ^[a-z0-9]{8,16}$  ;  LAKEHOUSE_RESOURCE_SUFFIX MUST equal LAKEHOUSE_TEST_RUN_ID
#
# Activation is ALL-OR-NOTHING (plan 1.17.2): if ANY overlay variable is set,
# every required variable must be present and valid — otherwise the caller
# aborts non-zero and MUST NOT fall back to the real stack.
#
# Bare RESOURCE_SUFFIX / PORT_OFFSET (without the LAKEHOUSE_ prefix) are not
# valid names anywhere and are ignored (plan 1.16.1, 1.18.8).
# ---------------------------------------------------------------------------

# The base compose files the CLI itself dispatches — the "active base set"
# (plan 1.16.6). Overlays (*.test.yml) are never part of this set.
OVERLAY_BASE_SERVICES=(spark41 kafka unity-catalog airflow mlflow notebooks dashboard)

# Run-id format gate (plan 1.16.1 / 1.18.8).
overlay_runid_valid() {
    [[ "${1:-}" =~ ^[a-z0-9]{8,16}$ ]]
}

# True (0) if ANY overlay variable is set — the trigger for all-or-nothing.
overlay_any_var_set() {
    [[ -n "${LAKEHOUSE_TEST_RUN_ID:-}" \
    || -n "${LAKEHOUSE_OVERLAY_DIR:-}" \
    || -n "${LAKEHOUSE_RESOURCE_SUFFIX:-}" \
    || -n "${LAKEHOUSE_PORT_OFFSET:-}" \
    || -n "${LAKEHOUSE_ENV_FILE:-}" ]]
}

# Validate the activation contract.
#   - No overlay var set        -> OVERLAY_ACTIVE=false, return 0 (default path).
#   - Any set + all valid       -> OVERLAY_ACTIVE=true, exports COMPOSE_PROJECT_NAME, return 0.
#   - Any set + anything invalid-> return non-zero, prints why, OVERLAY_ACTIVE=false.
# Never leaves the caller in a "partially configured -> use real stack" state.
overlay_validate_activation() {
    OVERLAY_ACTIVE=false

    if ! overlay_any_var_set; then
        return 0
    fi

    local errs=()
    [[ -n "${LAKEHOUSE_TEST_RUN_ID:-}" ]]    || errs+=("LAKEHOUSE_TEST_RUN_ID is required when any overlay variable is set")
    [[ -n "${LAKEHOUSE_OVERLAY_DIR:-}" ]]    || errs+=("LAKEHOUSE_OVERLAY_DIR is required when any overlay variable is set")
    [[ -n "${LAKEHOUSE_RESOURCE_SUFFIX:-}" ]] || errs+=("LAKEHOUSE_RESOURCE_SUFFIX is required when any overlay variable is set")

    if [[ -n "${LAKEHOUSE_TEST_RUN_ID:-}" ]] && ! overlay_runid_valid "${LAKEHOUSE_TEST_RUN_ID}"; then
        errs+=("LAKEHOUSE_TEST_RUN_ID '${LAKEHOUSE_TEST_RUN_ID}' is not of the form ^[a-z0-9]{8,16}\$")
    fi
    if [[ -n "${LAKEHOUSE_RESOURCE_SUFFIX:-}" && "${LAKEHOUSE_RESOURCE_SUFFIX:-}" != "${LAKEHOUSE_TEST_RUN_ID:-}" ]]; then
        errs+=("LAKEHOUSE_RESOURCE_SUFFIX must equal LAKEHOUSE_TEST_RUN_ID")
    fi
    if [[ -n "${LAKEHOUSE_OVERLAY_DIR:-}" && ! -d "${LAKEHOUSE_OVERLAY_DIR}" ]]; then
        errs+=("LAKEHOUSE_OVERLAY_DIR '${LAKEHOUSE_OVERLAY_DIR}' is not a directory")
    fi
    if [[ -n "${LAKEHOUSE_PORT_OFFSET:-}" && ! "${LAKEHOUSE_PORT_OFFSET}" =~ ^[0-9]+$ ]]; then
        errs+=("LAKEHOUSE_PORT_OFFSET '${LAKEHOUSE_PORT_OFFSET}' is not a non-negative integer")
    fi
    if [[ -n "${LAKEHOUSE_ENV_FILE:-}" && ! -r "${LAKEHOUSE_ENV_FILE}" ]]; then
        errs+=("LAKEHOUSE_ENV_FILE '${LAKEHOUSE_ENV_FILE}' is not a readable file")
    fi

    if (( ${#errs[@]} > 0 )); then
        local e
        for e in "${errs[@]}"; do
            echo "overlay: ${e}" >&2
        done
        echo "overlay: refusing to run — overlay mode is all-or-nothing and will never fall back to the real stack" >&2
        return 1
    fi

    OVERLAY_ACTIVE=true
    export COMPOSE_PROJECT_NAME="ol-test-${LAKEHOUSE_TEST_RUN_ID}"
    return 0
}

# Effective container name for a base container name.
# Applies the one allow-listed PR #0 fix (mlflow -> mlflow-server) unconditionally,
# then run-scopes when the overlay is active.
resolve_container_name() {
    local base="${1:?container name required}"
    # Allow-listed PR #0 fix (T-1.5.11): the MLflow container is mlflow-server.
    if [[ "${base}" == "mlflow" ]]; then
        base="mlflow-server"
    fi
    if [[ "${OVERLAY_ACTIVE:-false}" == "true" ]]; then
        echo "${base}-${LAKEHOUSE_RESOURCE_SUFFIX}"
    else
        echo "${base}"
    fi
}

# Effective published port for a base port (adds the offset only under an
# active overlay that set one).
resolve_port() {
    local base="${1:?port required}"
    if [[ "${OVERLAY_ACTIVE:-false}" == "true" && -n "${LAKEHOUSE_PORT_OFFSET:-}" ]]; then
        echo $(( base + LAKEHOUSE_PORT_OFFSET ))
    else
        echo "${base}"
    fi
}

# Populate OVERLAY_COMPOSE_ARGS with the -f (and --env-file) arguments for one
# base service. Under an active overlay the sibling *.test.yml must exist.
# Overlay-inactive: just the base file.
#
# This is the START/STOP hot path, so it deliberately does NOT run
# `docker compose config` — that render validation lives in
# overlay_validate_all_services (activation preflight). Rendering here would let a
# transient render error abort a teardown and orphan run-scoped containers.
overlay_set_compose_args() {
    local svc="${1:?service required}"
    local base="docker-compose-${svc}.yml"
    OVERLAY_COMPOSE_ARGS=()

    # Storage (PostgreSQL + SeaweedFS) is deliberately UNSCOPED: one shared
    # instance on the fixed host ports 5432/8333 that every run reaches, isolating
    # instead by run-scoped DATABASE/bucket names inside it. It therefore ships no
    # `docker-compose-storage.test.yml`, and OVERLAY_BASE_SERVICES omits it. Always
    # resolve it to the base file only — even under an active overlay — so
    # `start storage` / `stop storage` (and the `start all` storage arm) never fail
    # with "required overlay file missing".
    if [[ "${svc}" == "storage" ]]; then
        OVERLAY_COMPOSE_ARGS=(-f "${base}")
        return 0
    fi

    if [[ "${OVERLAY_ACTIVE:-false}" != "true" ]]; then
        OVERLAY_COMPOSE_ARGS=(-f "${base}")
        return 0
    fi

    local overlay="${LAKEHOUSE_OVERLAY_DIR%/}/docker-compose-${svc}.test.yml"
    if [[ ! -f "${overlay}" ]]; then
        echo "overlay: required overlay file missing for '${svc}': ${overlay}" >&2
        return 1
    fi

    OVERLAY_COMPOSE_ARGS=(-f "${base}" -f "${overlay}")
    if [[ -n "${LAKEHOUSE_ENV_FILE:-}" ]]; then
        OVERLAY_COMPOSE_ARGS=(--env-file "${LAKEHOUSE_ENV_FILE}" "${OVERLAY_COMPOSE_ARGS[@]}")
    fi
    return 0
}

# Validate that every overlay file for the active base set exists AND that
# `docker compose config` renders successfully (plan 1.17.2 — activation
# preflight). This is the single place that renders; it is invoked from the
# introspection command, not from start/stop, so a render failure never blocks
# teardown. Aborts non-zero on the first missing file or failed render.
overlay_validate_all_services() {
    [[ "${OVERLAY_ACTIVE:-false}" == "true" ]] || return 0
    local svc
    for svc in "${OVERLAY_BASE_SERVICES[@]}"; do
        # Only the bases that actually ship in this repo.
        [[ -f "docker-compose-${svc}.yml" ]] || continue
        overlay_set_compose_args "${svc}" || return 1
        if ! docker compose "${OVERLAY_COMPOSE_ARGS[@]}" config -q >/dev/null 2>&1; then
            echo "overlay: 'docker compose config' failed to render for '${svc}' — aborting" >&2
            return 1
        fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# Standalone destructive-target validator (plan 1.18.2 / 1.19.2 / 1.19.4).
#
# Given a run-id and effective target names, accept iff EVERY name in EVERY
# provided class derives from the run-id. When --active false, accept
# unconditionally: production reset (overlay inactive) is unrestricted and must
# not reintroduce the 1.14.3 defect.
#
# Usage:
#   overlay_validate_targets --runid <id> [--active true|false] \
#       [--databases "a b"] [--buckets "x"] [--volumes "v1 v2"] [--containers "c1 c2"]
#
# Name rules (all embed the CURRENT run-id, so a different run's ol_test_* is
# refused — plan 1.17.3):
#   database  : ^ol_test_<runid>(_[a-z0-9_]+)?$
#   bucket    : ^ol-test-<runid>$
#   volume    : ^ol-test-<runid>_[a-z0-9_-]+$
#   container : ^[a-z0-9._-]+-<runid>$
# ---------------------------------------------------------------------------
overlay_validate_targets() {
    local runid="" active="true"
    local databases="" buckets="" volumes="" containers=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --runid)      runid="$2"; shift 2 ;;
            --active)     active="$2"; shift 2 ;;
            --databases)  databases="$2"; shift 2 ;;
            --buckets)    buckets="$2"; shift 2 ;;
            --volumes)    volumes="$2"; shift 2 ;;
            --containers) containers="$2"; shift 2 ;;
            *) echo "overlay_validate_targets: unknown arg '$1'" >&2; return 2 ;;
        esac
    done

    if [[ "${active}" != "true" ]]; then
        return 0
    fi

    if ! overlay_runid_valid "${runid}"; then
        echo "overlay_validate_targets: invalid or missing --runid" >&2
        return 2
    fi

    local db_re="^ol_test_${runid}(_[a-z0-9_]+)?$"
    local bucket_re="^ol-test-${runid}$"
    local vol_re="^ol-test-${runid}_[a-z0-9_-]+$"
    local ctr_re="^[a-z0-9._-]+-${runid}$"

    local name
    for name in ${databases}; do
        [[ "${name}" =~ ${db_re} ]] || { echo "overlay: database '${name}' is not scoped to run-id '${runid}'" >&2; return 1; }
    done
    for name in ${buckets}; do
        [[ "${name}" =~ ${bucket_re} ]] || { echo "overlay: bucket '${name}' is not scoped to run-id '${runid}'" >&2; return 1; }
    done
    for name in ${volumes}; do
        [[ "${name}" =~ ${vol_re} ]] || { echo "overlay: volume '${name}' is not scoped to run-id '${runid}'" >&2; return 1; }
    done
    for name in ${containers}; do
        [[ "${name}" =~ ${ctr_re} ]] || { echo "overlay: container '${name}' is not scoped to run-id '${runid}'" >&2; return 1; }
    done
    return 0
}
