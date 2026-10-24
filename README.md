# prospero-analytics

Host-side tooling and analysis for **ProsperoTrace** captures — the
on-console tracer lives in [rooklz/ProsperoTrace](https://github.com/rooklz/ProsperoTrace).

This repository is deliberately console-free: it only **consumes** the
JSONL event stream that the agent produces (`docs/EVENT_FORMAT.md`) and
turns it into queries, reports and comparisons. No console internals, no
kernel-facing code — pure data engineering on trace output.

## Tools

| Tool | Purpose |
|---|---|
| `host/receiver.py` | Capture server: listens for agent connections, writes `trace-<pid>-<ts>.jsonl`, optional live filters |
| `host/summarize.py` | Per-capture aggregation: call counts per function, first-seen order, drop totals |
| `host/tracediff.py` | Compare two captures: functions that surfaced, disappeared, or changed rate |
| `host/tracedb.py` | Import many captures into one SQLite database; query who calls what across runs |

## Quickstart

```sh
python3 host/receiver.py --port 9029 --out traces/
python3 host/summarize.py traces/trace-1234-*.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl --json diff.json

python3 host/tracedb.py import traces.db traces/*.jsonl     # idempotent; re-run as traces/ grows
python3 host/tracedb.py captures traces.db
python3 host/tracedb.py functions traces.db --top 30
python3 host/tracedb.py who traces.db 'sceKernel*'           # fn or mod.fn, glob patterns
python3 host/tracedb.py sql traces.db "SELECT fw, count(*) FROM captures GROUP BY fw"
```

`tracedb` stores `captures` (hello metadata, totals), `calls` (one row per
call, args in `a0`..`a5` as hex text), `drops`, and a `functions` view. The
`sql` command is read-only. For example, functions the 14.10 runs call that
no 13.40 run does:

```sql
SELECT DISTINCT k.mod, k.fn FROM calls k JOIN captures c ON c.id = k.capture_id WHERE c.fw = '14.10'
EXCEPT
SELECT DISTINCT k.mod, k.fn FROM calls k JOIN captures c ON c.id = k.capture_id WHERE c.fw = '13.40'
```

## Tests

```sh
tests/run.sh
```

Drives smoke checks against synthetic captures: `tracediff` output, malformed-line
tolerance in `summarize`/`tracediff`, the receiver over loopback, and
`tracedb` import plus queries.

## Roadmap

- Query layer on top of `tracedb`: canned cross-capture reports (common
  surface, per-firmware diffs) beyond the raw `sql` command
- Web dashboard: per-run timelines, module dependency graphs
- NID coverage visualization (which known functions did this run touch)
- Arg-pattern clustering (callers, value ranges, threading behavior)
- CI fixtures: regenerate captures on a fixture console and diff

The output of these tools is the ground-truth dataset behind
firmware-compatibility questions (e.g. which API surface a newer title
needs) and behind validating compatibility-layer library implementations.

## License

MIT. Clean-room: no Sony material, no console internals.