#!/usr/bin/env bash
# Regenerate the architecture diagrams (SVG -> PNG @2x).
# Requires: python3, rsvg-convert (librsvg).
#   brew install librsvg     # rsvg-convert
# Usage: docs/img/render.sh
set -euo pipefail
cd "$(dirname "$0")"

python3 _gen_diagrams.py

for f in architecture-light architecture-dark medallion-flow-light medallion-flow-dark; do
  rsvg-convert -z 2 "$f.svg" -o "$f.png"
  echo "rendered $f.png"
done
