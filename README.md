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

## Quickstart

```sh
python3 host/receiver.py --port 9029 --out traces/
python3 host/summarize.py traces/trace-1234-*.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl
python3 host/tracediff.py traces/before.jsonl traces/after.jsonl --json diff.json
```

## Tests

```sh
tests/run.sh
```

Drives smoke checks against synthetic captures: `tracediff` output, malformed-line
tolerance in `summarize`/`tracediff`, and the receiver over loopback.

## Roadmap

- SQLite import + a real query layer over many captures
- Web dashboard: per-run timelines, module dependency graphs
- NID coverage visualization (which known functions did this run touch)
- Arg-pattern clustering (callers, value ranges, threading behavior)
- CI fixtures: regenerate captures on a fixture console and diff

The output of these tools is the ground-truth dataset behind
firmware-compatibility questions (e.g. which API surface a newer title
needs) and behind validating compatibility-layer library implementations.

## License

MIT. Clean-room: no Sony material, no console internals.