#!/usr/bin/env python3
"""summarize.py — aggregate a ProsperoTrace JSONL capture.

Prints call counts per module.function, first-seen order, drop totals, and
the top-N hottest functions. Useful for answering "which parts of the OS
surface does this program actually touch?"
"""
import argparse
import collections
import json
import sys

import tracefile

def load(paths):
    for path in paths:
        yield from tracefile.events(path)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json", metavar="FILE", default=None,
                    help="also write every function's count and first seq (use - for stdout only)")
    args = ap.parse_args()

    counts = collections.Counter()
    first_seen = {}
    drops = 0
    calls = 0
    for ev in load(args.files):
        t = ev.get("type")
        if t == "call":
            key = f"{ev.get('mod','?')}.{ev.get('fn','?')}"
            counts[key] += 1
            first_seen.setdefault(key, ev.get("seq", 0))
            calls += 1
        elif t == "drops":
            drops += ev.get("n", 0)

    if args.json:
        out = {"calls": calls, "unique": len(counts), "drops": drops,
               "functions": [{"function": k, "count": n, "first_seq": first_seen[k]}
                             for k, n in counts.most_common()]}
        text = json.dumps(out, indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
            return
        with open(args.json, "w") as f:
            f.write(text + "\n")

    print(f"{calls} calls, {len(counts)} unique functions, {drops} dropped\n")
    print(f"{'count':>8}  {'first seq':>10}  function")
    for key, n in counts.most_common(args.top):
        print(f"{n:>8}  {first_seen[key]:>10}  {key}")
    if args.json:
        print(f"\n[json] {args.json}")

    unknown = sum(n for k, n in counts.items() if k.split(".", 1)[1].startswith("nid_"))
    if unknown:
        print(f"\nnote: {unknown} calls hit unnamed NIDs — extend agent/data/nids.txt in ProsperoTrace", file=sys.stderr)

if __name__ == "__main__":
    main()
