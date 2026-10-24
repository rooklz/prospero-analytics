#!/bin/sh
# tracediff_smoke.sh — sanity check for host/tracediff.py against synthetic traces.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/base.jsonl" <<'EOF'
{"type":"hello","pid":1,"title":"demo","fw":"13.40","seq":0}
{"type":"call","seq":1,"mod":"libkernel","fn":"sceKernelOpen","args":[],"ret":"0x5"}
{"type":"call","seq":2,"mod":"libkernel","fn":"sceKernelClose","args":[],"ret":"0x0"}
{"type":"call","seq":3,"mod":"libSceVideoOut","fn":"sceVideoOutOpen","args":[],"ret":"0x1"}
EOF
cat > "$WORK/new.jsonl" <<'EOF'
{"type":"hello","pid":1,"title":"demo","fw":"14.10","seq":0}
{"type":"call","seq":1,"mod":"libkernel","fn":"sceKernelOpen","args":[],"ret":"0x5"}
{"type":"call","seq":2,"mod":"libkernel","fn":"sceKernelOpen","args":[],"ret":"0x5"}
{"type":"call","seq":3,"mod":"libkernel","fn":"sceKernelClose","args":[],"ret":"0x0"}
{"type":"call","seq":4,"mod":"libSceAudioOut","fn":"sceAudioOutOpen","args":[],"ret":"0x3"}
EOF

OUT=$("$ROOT/host/tracediff.py" "$WORK/base.jsonl" "$WORK/new.jsonl")
printf '%s\n' "$OUT" | grep -q "sceAudioOutOpen"          || { echo "FAIL: surfaced fn missing" >&2; exit 1; }
printf '%s\n' "$OUT" | grep -q "sceVideoOutOpen"          || { echo "FAIL: gone fn missing" >&2; exit 1; }
printf '%s\n' "$OUT" | grep -q "sceKernelOpen"            || { echo "FAIL: changed fn missing" >&2; exit 1; }
printf '%s\n' "$OUT" | grep -q "+1"                       || { echo "FAIL: delta missing" >&2; exit 1; }

"$ROOT/host/tracediff.py" "$WORK/base.jsonl" "$WORK/new.jsonl" --json "$WORK/diff.json"
grep -q '"surfaced"' "$WORK/diff.json"                      || { echo "FAIL: json missing surfaced" >&2; exit 1; }
grep -q '"delta": 1' "$WORK/diff.json"                      || { echo "FAIL: json delta wrong" >&2; exit 1; }

echo "tracediff_smoke: OK"