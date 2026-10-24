#!/bin/sh
# reports_smoke.sh — tracedb reports, dashboard, summarize --json, tracediff --normalize.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
DB="$WORK/t.db"
T="$ROOT/host/tracedb.py"

fail() { echo "FAIL: $1" >&2; [ $# -gt 1 ] && printf '%s\n' "$2" >&2; exit 1; }

call() { printf '{"type":"call","seq":%s,"tid":%s,"mod":"%s","fn":"%s","args":["%s","0x0","0x0","0x0","0x0","0x0"],"ret":"0x0"}\n' "$@"; }
{ echo '{"type":"hello","pid":1,"title":"echo","fw":"13.40","seq":0}'
  call 1 100 libkernel sceKernelOpen 0x10
  call 2 100 libkernel sceKernelOpen 0x20
  call 3 101 libkernel sceKernelClose 0x5
  call 4 100 libkernel sceKernelClose 0x5; } > "$WORK/a.jsonl"
{ echo '{"type":"hello","pid":2,"title":"echo","fw":"14.10","seq":0}'
  i=1; while [ $i -le 8 ]; do call $i 100 libkernel sceKernelOpen 0x10; i=$((i + 1)); done
  call 9 100 libkernel sceKernelClose 0x5
  call 10 100 libSceNet sceNetSocket 0x2; } > "$WORK/b.jsonl"
cat > "$WORK/nids.txt" <<'EOF2'
# module function nid
libkernel sceKernelOpen 0x1
libkernel sceKernelClose 0x2
libkernel sceKernelRead 0x3
libSceNet sceNetSocket 0x4
EOF2

"$T" import "$DB" "$WORK/a.jsonl" "$WORK/b.jsonl" > /dev/null

OUT=$("$T" common "$DB")
[ "$(printf '%s\n' "$OUT" | grep -c libkernel)" = 2 ] || fail "common surface wrong" "$OUT"
printf '%s\n' "$OUT" | grep -q sceNetSocket && fail "common includes a one-run function" "$OUT"

OUT=$("$T" fwdiff "$DB" 13.40 14.10)
printf '%s\n' "$OUT" | grep -Eq "^\+14.10 +libSceNet +sceNetSocket +1 +1" || fail "fwdiff wrong" "$OUT"
[ "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" = 2 ] || fail "fwdiff extra rows" "$OUT"

OUT=$("$T" coverage "$DB" "$WORK/nids.txt")
printf '%s\n' "$OUT" | grep -Eq "^libkernel +3 +2 +66.7" || fail "coverage pct wrong" "$OUT"
printf '%s\n' "$OUT" | grep -q "3/4 known functions touched" || fail "coverage total wrong" "$OUT"
OUT=$("$T" coverage "$DB" "$WORK/nids.txt" --missing)
printf '%s\n' "$OUT" | grep -q sceKernelRead || fail "coverage --missing wrong" "$OUT"

OUT=$("$T" args "$DB" sceKernelOpen --capture 1)
printf '%s\n' "$OUT" | grep -q "2 calls matching 'sceKernelOpen' from 1 threads in 1 captures" || fail "args header" "$OUT"
printf '%s\n' "$OUT" | grep -Eq "^a0 +2 +0x10 +0x20 " || fail "args a0 range" "$OUT"

python3 "$ROOT/host/dashboard.py" "$DB" -o "$WORK/r.html" > /dev/null
grep -q "<svg" "$WORK/r.html" && grep -q "libSceNet" "$WORK/r.html" && grep -q "#2 echo" "$WORK/r.html" \
    || fail "dashboard missing content"

python3 "$ROOT/host/summarize.py" "$WORK/b.jsonl" --json - | grep -q '"count": 8' || fail "summarize json"

OUT=$(python3 "$ROOT/host/tracediff.py" "$WORK/a.jsonl" "$WORK/b.jsonl" --normalize)
printf '%s\n' "$OUT" | grep -q "per 1000 calls" || fail "normalize header" "$OUT"
printf '%s\n' "$OUT" | grep -Eq "sceKernelClose +500.0 -> 100.0" || fail "normalized rate wrong" "$OUT"

echo "reports_smoke: OK"
