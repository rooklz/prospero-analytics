#!/usr/bin/env python3
"""tracediff.py — compare two ProsperoTrace captures.

Answers the "API surface drift" question:

  what functions did run A call that run B did not (and vice versa) at
  what relative rates?

This is the primitive behind firmware-compatibility work: point it at a
trace of the same workload before/after a change, or at two runs that are
supposed to behave alike, and it prints exactly which OS functions appear
or disappear from the call surface.

Output: human-readable report to stdout; `--json FILE` writes the structured
diff (used by CI and the dashboard).
"""
import argparse
import collections
import json
import sys

def load(path):
    counts = collections.Counter()
    first = {}
    totals = {"calls": 0, "drops": 0}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "call":
                key = (ev.get("mod", "?"), ev.get("fn", "?"))
                counts[key] += 1
                first.setdefault(key, ev.get("seq", 0))
                totals["calls"] += 1
            elif t == "drops":
                totals["drops"] += int(ev.get("n", 0))
    return counts, first, totals

def fmt_key(k):
    return f"{k[0]}.{k[1]}"

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="baseline trace (.jsonl)")
    ap.add_argument("new", help="comparison trace (.jsonl)")
    ap.add_argument("--json", metavar="FILE", default=None,
                    help="also write the structured diff (use - for stdout)")
    ap.add_argument("--top", type=int, default=20, help="rows in the changed-rate list")
    args = ap.parse_args()

    b_count, b_first, b_tot = load(args.base)
    n_count, n_first, n_tot = load(args.new)

    keys = set(b_count) | set(n_count)
    only_new, only_base, both = [], [], []
    for k in sorted(keys, key=lambda k: (k[0], k[1])):
        cb, cn = b_count.get(k, 0), n_count.get(k, 0)
        if cn and not cb:
            only_new.append(k)
        elif cb and not cn:
            only_base.append(k)
        else:
            both.append(k)

    changed = sorted(
        (k for k in both if b_count[k] != n_count[k]),
        key=lambda k: abs(n_count[k] - b_count[k]), reverse=True)

    print(f"base: {b_tot['calls']} calls, {len(b_count)} unique, {b_tot['drops']} dropped")
    print(f"new:  {n_tot['calls']} calls, {len(n_count)} unique, {n_tot['drops']} dropped")
    print()

    if only_new:
        print(f"only in NEW (surfaced here): {len(only_new)}")
        for k in only_new:
            print(f"  + {fmt_key(k):<44} {n_count[k]:>8}")
        print()

    if only_base:
        print(f"only in BASE (gone here): {len(only_base)}")
        for k in only_base:
            print(f"  - {fmt_key(k):<44} {b_count[k]:>8}")
        print()

    if changed:
        print(f"rate changes (top {args.top} by |delta|):")
        for k in changed[:args.top]:
            d = n_count[k] - b_count[k]
            print(f"  {fmt_key(k):<44} {b_count[k]:>8} -> {n_count[k]:<8} ({d:+d})")
        print()

    if args.json:
        out = {
            "base": {"calls": b_tot["calls"], "unique": len(b_count), "drops": b_tot["drops"]},
            "new": {"calls": n_tot["calls"], "unique": len(n_count), "drops": n_tot["drops"]},
            "surfaced": [{"mod": k[0], "fn": k[1], "count": n_count[k]} for k in only_new],
            "gone": [{"mod": k[0], "fn": k[1], "count": b_count[k]} for k in only_base],
            "changed": [{"mod": k[0], "fn": k[1], "base": b_count[k], "new": n_count[k],
                         "delta": n_count[k] - b_count[k]} for k in changed],
        }
        text = json.dumps(out, indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.json, "w") as f:
                f.write(text + "\n")
            print(f"[json] {args.json}")

if __name__ == "__main__":
    main()