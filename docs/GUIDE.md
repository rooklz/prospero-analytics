# ProsperoTrace end to end

Two repositories, one pipeline:

```
console (PS5)                          host (this repo)
ProsperoTrace agent ──JSONL/TCP──▶ receiver ─▶ validate ─▶ tracedb ─▶ dashboard
  hooks a payload's imports          │                       │
                                     └──── tracediff / fixture baseline
```

The agent produces events in the format of [EVENT_FORMAT.md](EVENT_FORMAT.md);
`host/validate.py` enforces it, so either side changing the format fails CI.

## 1. Set up

- Console: running the homebrew enabler with elfldr on 9021 and FTP on 2121.
- Host: Python 3.10+, and for building the agent the
  [ps5-payload-sdk](https://github.com/ps5-payload-dev/sdk) with LLVM.
- Clone both repositories side by side:
  [ProsperoTrace](https://github.com/rooklz/ProsperoTrace) and this one.

## 2. Trace a program

On the host, start a session; it receives, validates, imports and renders:

```sh
python3 host/session.py --out session/ --captures 1 --timeout 300
```

On the console side, configure and launch the agent (from ProsperoTrace):

```sh
printf 'PT_HOST=<host ip>\nPT_PID=<target pid>\n' > prosperotrace.conf
curl -T prosperotrace.conf ftp://<console ip>:2121/data/prosperotrace.conf
PS5_IP=<console ip> ./deploy.sh build/prosperotrace.elf
```

When the target exits (or the agent is stopped), the session prints a
summary and leaves `session/traces/*.jsonl`, `session/traces.db` and
`session/report.html`.

## 3. Read the results

```sh
open session/report.html                              # timelines, module matrix
python3 host/tracedb.py functions session/traces.db   # hottest functions
python3 host/tracedb.py args session/traces.db recv   # how recv is called
python3 host/tracedb.py coverage session/traces.db ../ProsperoTrace/agent/data/nids.txt
```

Add more sessions to the same database with `tracedb.py import`, then use
`common`, `fwdiff` and `sql` across all of them.

## 4. Check for regressions

`session.py --baseline FILE` fails if a capture's API surface differs from
FILE. ProsperoTrace's `tools/fixture.sh` does this for its `ptdemo` payload
against `tests/fixtures/ptdemo-baseline.jsonl`, and its "console fixture"
workflow runs it on the self-hosted `ps5` runner, publishing the capture,
its database and dashboard as artifacts.
