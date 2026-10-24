#!/usr/bin/env python3
"""validate.py — check captures against docs/EVENT_FORMAT.md.

The contract between the on-console agent (ProsperoTrace) and these tools.
A capture passes when its first event is a hello, every line is a usable
event (tracefile's rule), seq strictly increases, call events carry the
stable keys with the documented types (args: six hex strings, ret/nid hex,
ts/tid non-negative integers), and drops carry n.

    python3 host/validate.py traces/trace-*.jsonl
    python3 host/validate.py capture.jsonl --json report.json

Exit 0 when every file passes, 1 otherwise. ProsperoTrace's fixture runs
this on each console capture, so a format change on either side fails CI.
"""
import argparse
import json
import re
import sys

import tracefile

HEX = re.compile(r"^0x[0-9a-f]+$")

def _count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0

def check_call(ev):
    errs = []
    for k in ("seq", "ts", "tid"):
        if not _count(ev.get(k)):
            errs.append(f"{k} missing or not a non-negative integer")
    for k in ("mod", "fn"):
        if not isinstance(ev.get(k), str) or not ev.get(k):
            errs.append(f"{k} missing or empty")
    for k in ("nid", "ret"):
        if not isinstance(ev.get(k), str) or not HEX.match(ev[k]):
            errs.append(f"{k} not a lowercase hex string")
    args = ev.get("args")
    if not isinstance(args, list) or len(args) != 6 or \
            not all(isinstance(a, str) and HEX.match(a) for a in args):
        errs.append("args not six hex strings")
    return errs

def validate(path, limit=20):
    problems, counts, last_seq = [], {"hello": 0, "call": 0, "drops": 0, "other": 0}, -1
    first = True
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            ev = tracefile.parse(line)
            if ev is None:
                problems.append((n, "not a valid event"))
                continue
            t = ev.get("type")
            counts[t if t in counts else "other"] += 1
            if first and t != "hello":
                problems.append((n, "first record is not hello"))
            first = False
            if t == "hello":
                if not _count(ev.get("pid")):
                    problems.append((n, "hello pid missing"))
                for k in ("title", "fw"):
                    if not isinstance(ev.get(k), str):
                        problems.append((n, f"hello {k} missing"))
            elif t == "call":
                problems += [(n, e) for e in check_call(ev)]
            elif t == "drops":
                if not _count(ev.get("n")):
                    problems.append((n, "drops n missing"))
            else:
                problems.append((n, f"unknown type {t!r}"))
            seq = ev.get("seq")
            if _count(seq):
                if seq <= last_seq:
                    problems.append((n, f"seq {seq} not after {last_seq}"))
                last_seq = seq
    if counts["hello"] == 0:
        problems.append((0, "no hello record"))
    return {"path": path, "ok": not problems, "counts": counts,
            "problems": [{"line": l, "error": e} for l, e in problems[:limit]],
            "problem_count": len(problems)}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", metavar="FILE", default=None, help="also write the reports (- for stdout only)")
    args = ap.parse_args()
    reports = [validate(p) for p in args.files]
    if args.json != "-":
        for r in reports:
            c = r["counts"]
            print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['path']}: {c['call']} calls, {c['drops']} drops"
                  f"{'' if r['ok'] else ', %d problems' % r['problem_count']}")
            for p in r["problems"]:
                print(f"     line {p['line']}: {p['error']}")
    if args.json:
        text = json.dumps(reports, indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.json, "w") as f:
                f.write(text + "\n")
    sys.exit(0 if all(r["ok"] for r in reports) else 1)

if __name__ == "__main__":
    main()
