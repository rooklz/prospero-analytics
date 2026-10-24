#!/bin/sh
# run.sh — drive the host-side checks.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for t in tracediff_smoke.sh malformed_smoke.sh receiver_smoke.py tracedb_smoke.sh reports_smoke.sh session_smoke.py corpus_smoke.py; do
    "$ROOT/tests/$t" > "$WORK/out" 2>&1 || { cat "$WORK/out"; exit 1; }
done
rm -f "$WORK/out"

echo "all tests passed"