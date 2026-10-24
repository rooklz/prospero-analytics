# Contributing

Thanks for helping with the analytics tooling. Scope and conventions:

## Scope

This repo is **host-side only**. It consumes trace captures (JSONL per
`docs/EVENT_FORMAT.md`) and produces reports, queries and comparisons. The
on-console tracer and anything that touches the console runtime lives in
the sibling repo [rooklz/ProsperoTrace](https://github.com/rooklz/ProsperoTrace).

If a change needs a new field in the event stream, add it to
`docs/EVENT_FORMAT.md` here (compatibility rules apply), not only to the
consumer.

## Getting started

```sh
tests/run.sh        # all checks
```

All tools target Python 3 with the standard library only — no third-party
dependencies.

## Conventions

- One tool per file under `host/`, runnable as `python3 host/<tool>.py`.
- Every tool prints a human-readable report to stdout; structured output is
  opt-in via a `--json FILE` flag (`-` for stdout).
- Use `argparse` with helper text that explains the *use case*, not just the
  flags.
- Tolerate malformed lines: skip them, never abort the whole capture.
- Keep the stable keys documented in `EVENT_FORMAT.md` untouched; new keys
  are additive. `args` is always six entries.
- Add (or extend) a smoke test under `tests/` for every new tool; wire it
  into `tests/run.sh`.
- Every CLI tool needs an example in the README quickstart.
- Shared parsing lives in `host/tracefile.py`; read captures through it.

## Tests

Host-side checks must stay dependency-free and fast. Synthetic fixtures
over fixture captures (as in `tests/tracediff_smoke.sh`) are preferred to
bundling real traces — this repo ships no captures.

## License

MIT; contributions are accepted under it.