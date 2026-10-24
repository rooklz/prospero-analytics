#!/bin/sh
# run.sh — drive the host-side checks.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

"$ROOT/tests/tracediff_smoke.sh" > "$WORK/out" || { cat "$WORK/out"; exit 1; }
rm -f "$WORK/out"

echo "all tests passed"