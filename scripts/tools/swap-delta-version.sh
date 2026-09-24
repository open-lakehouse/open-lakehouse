#!/usr/bin/env bash
# swap-delta-version.sh — put a specific Delta build on the live Spark classpath,
# so the T4 version-change matrix can prove the GOOD pin passes and the KNOWN-BAD
# pins fail the way docs/testing.md says they do (Delta 4.3.0 → UC-connector NPE;
# 4.2.0 → no catalog-managed Delta; 4.0.x → LogKey NoSuchMethodError).
#
# It edits the *live, gitignored* config/spark/spark-defaults.conf only — never a
# tracked file — so a CI runner can rehearse a bad version and throw the tree away.
# It deliberately fetches versions that jars.sha256 does not pin: proving a bad
# version fails is the whole point, so no checksum lock applies here.
#
# Usage: swap-delta-version.sh <delta-version>      # e.g. 4.3.1, 4.3.0, 4.2.0
#        (run from the repo root; restart spark-master-41 afterwards)
set -euo pipefail

VER="${1:?usage: swap-delta-version.sh <delta-version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
JARS_DIR="$ROOT/jars"
LIVE="$ROOT/config/spark/spark-defaults.conf"
EXAMPLE="$ROOT/config/spark/spark-defaults.conf.example"
MAVEN_BASE_URL="${MAVEN_BASE_URL:-https://repo1.maven.org/maven2}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

mkdir -p "$JARS_DIR"
[ -f "$LIVE" ] || cp "$EXAMPLE" "$LIVE"

fetch() {  # $1 = maven path, $2 = output filename
  local url="$MAVEN_BASE_URL/$1" out="$JARS_DIR/$2"
  [ -f "$out" ] && { echo "  have $2"; return 0; }
  echo "  fetching $2"
  if command -v curl >/dev/null 2>&1; then curl -fsSL -o "$out.tmp" "$url"
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$out.tmp" "$url"
  else echo -e "${RED}no curl/wget${NC}" >&2; return 1; fi
  mv "$out.tmp" "$out"
}

echo "Swapping Delta -> $VER"
fetch "io/delta/delta-spark_2.13/$VER/delta-spark_2.13-$VER.jar" "delta-spark_2.13-$VER.jar"
fetch "io/delta/delta-storage/$VER/delta-storage-$VER.jar"       "delta-storage-$VER.jar"

# Repoint every delta-spark_2.13-*.jar / delta-storage-*.jar reference in the live
# conf at the requested version. Portable sed (macOS + GNU): write to a temp file.
tmp="$(mktemp)"
sed -E \
  -e "s#delta-spark_2\.13-[0-9]+\.[0-9]+\.[0-9]+\.jar#delta-spark_2.13-${VER}.jar#g" \
  -e "s#delta-storage-[0-9]+\.[0-9]+\.[0-9]+\.jar#delta-storage-${VER}.jar#g" \
  "$LIVE" > "$tmp"
mv "$tmp" "$LIVE"
# mktemp creates 0600; `mv` preserves it, leaving spark-defaults.conf readable
# only by the runner user. The Spark container runs as a different (non-root)
# uid and mounts this file at /opt/spark/conf/spark-defaults.conf, so spark-submit
# fails with "Permission denied" BEFORE any Delta code loads — which made every
# matrix leg fail identically (a false negative-gate pass). Keep it world-readable.
chmod 0644 "$LIVE"

if grep -q "delta-spark_2.13-${VER}.jar" "$LIVE"; then
  echo -e "${GREEN}live spark-defaults.conf now points at Delta ${VER}${NC}"
else
  echo -e "${YELLOW}⚠ no delta-spark reference found to rewrite in ${LIVE#"$ROOT"/}${NC}" >&2
fi
