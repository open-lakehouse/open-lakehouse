#!/usr/bin/env bash
# Preflight check for open-lakehouse. Exits 0 if ready to start, non-zero otherwise.
# This is a thin wrapper that defers to `./lakehouse preflight` (which lives in the
# main CLI). It exists so the lakehouse-lifecycle skill can invoke it by a stable
# relative path without depending on the user's PATH.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

if [[ ! -x "$PROJECT_ROOT/lakehouse" ]]; then
    echo "✗ lakehouse CLI not found at $PROJECT_ROOT/lakehouse"
    exit 2
fi

exec "$PROJECT_ROOT/lakehouse" preflight
