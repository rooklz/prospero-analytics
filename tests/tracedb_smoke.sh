#!/bin/sh
# tracedb_smoke.sh — import synthetic captures into SQLite and query them.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
DB="$WORK/t.db"
T="$ROOT/host/tracedb.py"

fail() { echo "FAIL: $1" >&2; [ $# -gt 1 ] && printf '%s\n' "$2" >&2; exit 1; }

cat > "$WORK/a.jsonl" <<'EOF'
{"type":"hello","pid":11,"title":"echo","fw":"13.40","seq":0}
{"type":"call","seq":1,"ts":5,"tid":100,"mod":"libkernel","fn":"sceKernelOpen","nid":"0x1","args":["0x2000","0x0","0x0","0x0","0x0","0x0"],"ret":"0x5"}
{"type":"call","seq":2,"ts":6,"tid":100,"mod":"libkernel","fn":"sceKernelRead","nid":"0x2","args":["0x5","0x3000","0x100","0x0","0x0","0x0"],"ret":"0x100"}
{"type":"drops","seq":3,"n":4}
not json
{"type":"call","seq":4,"ts":7,"tid":101,"mod":"libkernel","fn":"sceKernelClose","nid":"0x3","args":["0x5","0x0","0x0","0x0","0x0","0x0"],"ret":"0x0"}
EOF
cat > "$WORK/b.jsonl" <<'EOF'
{"type":"hello","pid":12,"title":"echo","fw":"14.10","seq":0}
{"type":"call","seq":1,"mod":"libkernel","fn":"sceKernelOpen","args":["0x2000","0x0","0x0","0x0","0x0","0x0"],"ret":"0x5"}
{"type":"call","seq":2,"mod":"libSceNet","fn":"sceNetSocket","args":["0x0","0x2","0x1","0x0","0x0","0x0"],"ret":"0x7"}
EOF

OUT=$("$T" import "$DB" "$WORK/a.jsonl" "$WORK/b.jsonl")
printf '%s\n' "$OUT" | grep -q "1 malformed lines skipped"  || fail "malformed line not counted" "$OUT"
printf '%s\n' "$OUT" | grep -q ": 2 captures, 5 calls"       || fail "import totals wrong" "$OUT"

OUT=$("$T" import "$DB" "$WORK/a.jsonl")
printf '%s\n' "$OUT" | grep -q "already imported"            || fail "re-import not skipped" "$OUT"

# a capture that was still growing replaces its earlier rows
echo '{"type":"call","seq":3,"mod":"libSceNet","fn":"sceNetSend","args":["0x7","0x0","0x0","0x0","0x0","0x0"],"ret":"0x10"}' >> "$WORK/b.jsonl"
OUT=$("$T" import "$DB" "$WORK/b.jsonl")
printf '%s\n' "$OUT" | grep -q ": 2 captures, 6 calls"       || fail "grown capture not replaced" "$OUT"

if "$T" import "$DB" "$WORK/missing.jsonl" > /dev/null 2>&1; then fail "missing file not reported"; fi

OUT=$("$T" functions "$DB")
printf '%s\n' "$OUT" | grep -Eq "^2 +2 +libkernel +sceKernelOpen" || fail "functions row wrong" "$OUT"

OUT=$("$T" who "$DB" 'libSceNet.*' --json -)
[ "$(printf '%s\n' "$OUT" | grep -c '"capture": 2')" = 2 ] || fail "who mod.fn pattern wrong" "$OUT"
OUT=$("$T" who "$DB" sceKernelRead)
printf '%s\n' "$OUT" | grep -Eq "^1 +echo +13.40 " || fail "who fn wrong" "$OUT"

OUT=$("$T" sql "$DB" "SELECT DISTINCT k.fn FROM calls k JOIN captures c ON c.id = k.capture_id WHERE c.fw = '14.10'
                       EXCEPT
                       SELECT DISTINCT k.fn FROM calls k JOIN captures c ON c.id = k.capture_id WHERE c.fw = '13.40'
                       ORDER BY 1")
[ "$OUT" = "$(printf 'fn\nsceNetSend\nsceNetSocket')" ] || fail "fw surface query wrong" "$OUT"

OUT=$("$T" sql "$DB" "SELECT a0, a1, a2, ret FROM calls WHERE fn = 'sceKernelRead'")
printf '%s\n' "$OUT" | grep -Eq "^0x5 +0x3000 +0x100 +0x100$" || fail "args not stored" "$OUT"

if "$T" sql "$DB" "DELETE FROM calls" > /dev/null 2>&1; then fail "sql is not read-only"; fi

"$T" captures "$DB" --json "$WORK/c.json" > /dev/null
grep -q '"fw": "14.10"' "$WORK/c.json"                       || fail "captures json missing fw"

echo "tracedb_smoke: OK"
