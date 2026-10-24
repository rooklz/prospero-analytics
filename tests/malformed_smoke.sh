#!/bin/sh
# malformed_smoke.sh — summarize and tracediff must skip bad lines, not abort.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/bad.jsonl" <<'EOF'
{"type":"hello","pid":1,"title":"demo","fw":"13.40","seq":0}
{"type":"call","seq":1,"mod":"libkernel","fn":"sceKernelOpen","args":["0x0","0x0","0x0","0x0","0x0","0x0"],"ret":"0x5"}
42
["not", "an", "event"]
{"type":"call","seq":2,"mod":"libkernel","fn":"sceKernelRe
{"type":"drops","seq":3,"n":null}
{"type":"drops","seq":4,"n":"many"}
{"type":"call","seq":"5","mod":"libkernel","fn":"sceKernelClose"}
{"type":"call","seq":6,"mod":"libkernel","fn":["sceKernelClose"]}
{"type":"drops","seq":7,"n":3}
{"type":"call","seq":8,"mod":"libkernel","fn":"sceKernelClose","args":["0x5","0x0","0x0","0x0","0x0","0x0"],"ret":"0x0"}
EOF

OUT=$(python3 "$ROOT/host/summarize.py" "$WORK/bad.jsonl")
printf '%s\n' "$OUT" | grep -q "^2 calls, 2 unique functions, 3 dropped" \
    || { echo "FAIL: summarize totals wrong:" >&2; printf '%s\n' "$OUT" >&2; exit 1; }

OUT=$(python3 "$ROOT/host/tracediff.py" "$WORK/bad.jsonl" "$WORK/bad.jsonl")
printf '%s\n' "$OUT" | grep -q "^base: 2 calls, 2 unique, 3 dropped" \
    || { echo "FAIL: tracediff totals wrong:" >&2; printf '%s\n' "$OUT" >&2; exit 1; }

echo "malformed_smoke: OK"
