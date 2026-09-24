#!/usr/bin/env bash
# verify-versions.sh — pin-consistency gate for the open-lakehouse jar set.
#
# Turns the version pins from prose claims into a checked invariant. Runs with
# no Docker and no network, so it can gate every PR (see
# tests/test_version_consistency.py and the e2e workflow preflight). It answers
# one question: do all the places that name a core jar version agree, and has a
# forbidden (known-broken) version or a JDBC-catalog path leaked into shipped
# config?
#
# SSOT is scripts/tools/download-jars.sh — it is what actually fetches the
# bytes. spark-defaults.conf.example, CLAUDE.md, and (locally) the live
# spark-defaults.conf must agree with it.
#
# Portable to bash 3.2 (macOS): no associative arrays, no ${x,,}.
# Exit 0 = consistent. Exit 1 = a mismatch a human must resolve before a bump.
set -euo pipefail

# --tracked-only: gate only git-tracked files (download-jars.sh, .example,
# CLAUDE.md) and skip the live spark-defaults.conf drift check. CI and the
# pytest wrapper use it so the merge gate never depends on a per-developer,
# gitignored file. A bare run (humans) also warns on live drift.
TRACKED_ONLY=0
REQUIRE_CHECKSUMS=0
for a in "$@"; do
  case "$a" in
    --tracked-only) TRACKED_ONLY=1 ;;
    # --require-checksums: fail if any pinned jar has no sha256 lock entry. Flip
    # this on in CI once jars.sha256 is generated (docs/testing.md supply chain).
    --require-checksums) REQUIRE_CHECKSUMS=1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DL="$ROOT/scripts/tools/download-jars.sh"
EXAMPLE="$ROOT/config/spark/spark-defaults.conf.example"
CLAUDE="$ROOT/CLAUDE.md"
LIVE="$ROOT/config/spark/spark-defaults.conf"   # gitignored; only present locally

fail=0
note() { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; fail=1; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }

for f in "$DL" "$EXAMPLE" "$CLAUDE"; do
  [ -f "$f" ] || { note "missing required file: ${f#"$ROOT"/}"; }
done
[ "$fail" -eq 0 ] || { echo "cannot verify — required files missing" >&2; exit 1; }

# jar filenames actually loaded onto the Spark classpath (value side of the
# spark.jars line only — never the key). basename each path, sorted unique.
jars_on_classpath() {  # $1 = conf file
  grep -E '^[[:space:]]*spark\.jars([[:space:]]|=)' "$1" \
    | sed -E 's/^[[:space:]]*spark\.jars[[:space:]=]+//' \
    | tr ',' '\n' \
    | sed -E 's#.*/##; s/^[[:space:]]+//; s/[[:space:]]+$//' \
    | grep -E '\.jar$' | sort -u
}

# Whole jar filenames that download-jars.sh fetches (field 1 of each
# "name.jar|url|size" entry), so family matches can anchor at ^ and never match
# a family name embedded in a longer filename (e.g. the AWS SDK v2 jar
# `bundle-2.24.6.jar` vs `aws-java-sdk-bundle-1.12.780.jar`).
dl_filenames() { grep -oE '"[A-Za-z0-9._-]+\.jar\|' "$DL" | sed -E 's/^"//; s/\|$//'; }
DOWNLOADED="$(dl_filenames | sort -u)"

# The first downloaded filename whose name STARTS with a family prefix. Empty
# if none. Anchored at ^ so 'bundle-' does not match 'aws-java-sdk-bundle-'.
dl_filename() { printf '%s\n' "$DOWNLOADED" | grep -E "^${1}[0-9]" | head -1; }
ver_of()      { printf '%s' "$1" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

CLASSPATH_JARS="$(jars_on_classpath "$EXAMPLE")"

# --- Required core jars: same filename in download-jars.sh AND on classpath ---
# family_regex | needs a version pinned in CLAUDE.md prose? (yes/no)
CORE="\
iceberg-spark-runtime-4.0_2.13-|yes
delta-spark_2.13-|yes
delta-storage-|no
unitycatalog-spark_2.13-|yes
unitycatalog-client-|yes
unitycatalog-hadoop-|yes
hadoop-aws-|no
aws-java-sdk-bundle-|no
bundle-|no"

echo "== required core jars: download-jars.sh <-> spark-defaults.conf.example =="
while IFS='|' read -r fam claude_pin; do
  [ -n "$fam" ] || continue
  fn="$(dl_filename "$fam")"
  if [ -z "$fn" ]; then note "download-jars.sh has no jar for family '${fam}*'"; continue; fi
  if printf '%s\n' "$CLASSPATH_JARS" | grep -qxF "$fn"; then
    ok "$fn — downloaded and on classpath"
  else
    note "$fn is downloaded but NOT on spark.jars in .example"
  fi
  if [ "$claude_pin" = "yes" ]; then
    v="$(ver_of "$fn")"
    if [ -n "$v" ] && grep -qF "$v" "$CLAUDE"; then
      ok "CLAUDE.md pins ${fam%-} $v"
    else
      note "CLAUDE.md does not pin ${fam%-} $v (prose drifted from the jar set)"
    fi
  fi
done <<EOF
$CORE
EOF

# --- Forbidden versions / catalog paths in SHIPPED CONFIG (never prose) ------
# CLAUDE.md is intentionally excluded: golden rule #1 *quotes* the JDBC keys as
# the anti-pattern to forbid, so finding them there is correct, not a defect.
FORBIDDEN_JAR="delta-spark_2.13-4.2.0 delta-spark_2.13-4.3.0 delta-storage-4.2.0 delta-storage-4.3.0 unitycatalog-spark_2.13-0.3.0 unitycatalog-client-0.3.0 unitycatalog-hadoop-0.3.0"
FORBIDDEN_CAT="spark.sql.catalog.iceberg.type=jdbc .jdbc.user .jdbc.password"

scan_forbidden() {  # $1 = file, rest = tokens
  local f="$1"; shift
  [ -f "$f" ] || return 0
  local squished; squished="$(tr -d '[:space:]' < "$f")"
  local tok
  for tok in "$@"; do
    if printf '%s' "$squished" | grep -qF "$(printf '%s' "$tok" | tr -d '[:space:]')"; then
      note "${f#"$ROOT"/} contains forbidden token: $tok"
    fi
  done
}

echo "== forbidden versions / JDBC-catalog paths (shipped config only) =="
# shellcheck disable=SC2086  # intentional word-split of the token lists
scan_forbidden "$DL" $FORBIDDEN_JAR
# shellcheck disable=SC2086
scan_forbidden "$EXAMPLE" $FORBIDDEN_JAR $FORBIDDEN_CAT
[ "$fail" -eq 0 ] && ok "no forbidden versions or JDBC-catalog paths in shipped config"

# --- Live spark-defaults.conf drift (local dev only) ------------------------
# The runtime config is gitignored, so CI never sees it. Locally, catch the
# exact drift class patch-01 fixes: a live conf whose classpath no longer
# matches the pinned set.
if [ "$TRACKED_ONLY" -eq 1 ]; then
  echo "== live spark-defaults.conf check skipped (--tracked-only) =="
elif [ -f "$LIVE" ]; then
  echo "== live spark-defaults.conf matches the pinned core jars =="
  live_cp="$(jars_on_classpath "$LIVE")"
  # shellcheck disable=SC2086
  scan_forbidden "$LIVE" $FORBIDDEN_JAR $FORBIDDEN_CAT
  while IFS='|' read -r fam _; do
    [ -n "$fam" ] || continue
    fn="$(dl_filename "$fam")"
    [ -n "$fn" ] || continue
    if printf '%s\n' "$live_cp" | grep -qxF "$fn"; then :; else
      note "live spark-defaults.conf is missing/mismatched core jar: $fn"
    fi
  done <<EOF
$CORE
EOF
  [ "$fail" -eq 0 ] && ok "live spark-defaults.conf matches the pinned core jars"
else
  echo "== live spark-defaults.conf not present (skipping local-drift check) =="
fi

# --- sha256 lock coverage (supply chain) ------------------------------------
# Every jar download-jars.sh fetches should have an entry in jars.sha256, so a
# re-published/tampered artifact is caught by hash, not just size. No network:
# this only checks that the lock COVERS the pinned set. Warns until the lock is
# generated; --require-checksums makes a gap fatal.
LOCK="$ROOT/scripts/tools/jars.sha256"
echo "== sha256 lock coverage =="
if [ ! -f "$LOCK" ]; then
  if [ "$REQUIRE_CHECKSUMS" -eq 1 ]; then note "jars.sha256 lock missing"; else
    printf '  \033[33m⚠\033[0m jars.sha256 missing — run download-jars.sh --lock\n'; fi
else
  missing=""
  while IFS= read -r jar; do
    [ -n "$jar" ] || continue
    if ! awk -v n="$jar" '$2==n{f=1} END{exit !f}' "$LOCK"; then
      missing="$missing $jar"
    fi
  done <<EOF
$DOWNLOADED
EOF
  if [ -n "$missing" ]; then
    if [ "$REQUIRE_CHECKSUMS" -eq 1 ]; then
      note "jars.sha256 missing entries for:"; printf '      %s\n' $missing >&2
    else
      printf '  \033[33m⚠\033[0m jars.sha256 not yet populated for:%s\n' "$missing"
      printf '     (run: ./scripts/tools/download-jars.sh --lock)\n'
    fi
  else
    ok "jars.sha256 covers all pinned jars"
  fi
fi

echo
if [ "$fail" -ne 0 ]; then
  echo -e "\033[31mversion consistency FAILED — resolve before changing a pin.\033[0m" >&2
  exit 1
fi
echo -e "\033[32mversion consistency OK.\033[0m"
