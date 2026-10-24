# prospero-analytics

[![tests](https://github.com/rooklz/prospero-analytics/actions/workflows/tests.yml/badge.svg)](https://github.com/rooklz/prospero-analytics/actions/workflows/tests.yml)
[![python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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
| `host/dashboard.py` | Static HTML report from a database: per-run timelines, capture x module matrix |
| `host/validate.py` | Check captures against `docs/EVENT_FORMAT.md` (the agent/host contract) |
| `host/session.py` | One session end to end: receive, validate, import, render, optional baseline diff |
| `host/catalogue.py` | Keep the corpus: import/list/export captures with filters and an `index.json` |
| `host/priority.py` | Coverage of a declared-function manifest + ranked implementation backlog (`--markdown`) |
| `host/parity.py` | Console-vs-desktop parity: missing/extra/drifted/matches worklist for a compatibility layer |
| `host/coveragemap.py` | Merge priority reports into one corpus-wide declared→seen matrix |

Start with [docs/GUIDE.md](docs/GUIDE.md) for the whole pipeline, console to
dashboard.

## Quickstart

```sh
python3 host/session.py --out session/ --captures 1        # receive+validate+import+report
python3 host/validate.py traces/trace-*.jsonl
python3 host/receiver.py --port 9029 --out traces/
python3 host/summarize.py traces/trace-1234-*.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl --json diff.json
python3 host/tracediff.py traces/short.jsonl traces/long.jsonl --normalize   # per-1000-call rates
python3 host/summarize.py traces/trace-1234-*.jsonl --json summary.json

python3 host/tracedb.py import traces.db traces/*.jsonl     # idempotent; re-run as traces/ grows
python3 host/tracedb.py captures traces.db
python3 host/tracedb.py functions traces.db --top 30
python3 host/tracedb.py who traces.db 'sceKernel*'           # fn or mod.fn, glob patterns
python3 host/tracedb.py common traces.db                     # functions every capture calls
python3 host/tracedb.py fwdiff traces.db 13.40 14.10         # called on one firmware, never the other
python3 host/tracedb.py coverage traces.db ../ProsperoTrace/agent/data/nids.txt [--missing]
python3 host/tracedb.py args traces.db sceKernelOpen         # per-slot distinct values, ranges, top values
python3 host/tracedb.py sql traces.db "SELECT fw, count(*) FROM captures GROUP BY fw"

python3 host/dashboard.py traces.db -o report.html           # self-contained page, no scripts

python3 host/catalogue.py import corpus.db traces/*.jsonl     # the corpus as a curated database
python3 host/catalogue.py list corpus.db --fw 13.40
python3 host/catalogue.py export corpus.db --title echo --out subset/

python3 host/priority.py traces/*.jsonl --manifest nids.txt                 # coverage + backlog
python3 host/priority.py traces/*.jsonl --manifest nids.txt --markdown      # implementation table
python3 host/priority.py traces/*.jsonl --manifest nids.txt --missing       # declared, never seen
python3 host/parity.py console.jsonl desktop.jsonl                          # missing/extra/drifted
python3 host/coveragemap.py backlog-*.json                                  # union coverage matrix
```

`tracedb` stores `captures` (hello metadata, totals), `calls` (one row per
call, args in `a0`..`a5` as hex text), `drops`, and a `functions` view. The
`sql` command is read-only. `fwdiff` is a canned form of this query, which
lists functions the 14.10 runs call that no 13.40 run does:

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
`tracedb` import plus every report, the dashboard, `validate` and `session`, and the `--json` /
`--normalize` flags. GitHub Actions runs them on Linux and macOS with
Python 3.10 and 3.14.

## Status

The roadmap is done: SQLite import and query layer (`tracedb`), dashboard
(`dashboard.py`), NID coverage (`tracedb coverage`, `priority.py`),
arg-pattern analysis (`tracedb args`, `priority.py` sketches), the corpus
(`catalogue.py`), console/desktop parity (`parity.py`), the coverage matrix
(`coveragemap.py`), CI, and the console fixture. The fixture lives with the
agent, in ProsperoTrace's `tools/fixture.sh`: it traces a demo payload on a
real console with this repo's receiver and fails if `tracediff` finds a
function that surfaced or disappeared against the stored baseline.

The output of these tools is the ground-truth dataset behind
firmware-compatibility questions (e.g. which API surface a newer title
needs) and behind validating compatibility-layer library implementations:
`priority.py` turns a set of captures plus a manifest of implemented
functions into a concrete "implement these next" list, and `parity.py` turns
a console/desktop pair into the exact missing-API worklist.

## License

MIT. Clean-room: no Sony material, no console internals.