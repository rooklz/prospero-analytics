#!/usr/bin/env python3
"""coveragemap.py — merge priority.py reports into one corpus-wide matrix.

A coverage map for a maintainer: for every declared function, how many of
the scoped reports saw a call to it, and the summed call count. Shows which
functions every traced workload needs (a stable core), which only niche
titles touch, and which nothing has called yet.

    python3 host/coveragemap.py backlog-a.json backlog-b.json
    python3 host/coveragemap.py backlog-*.json --markdown --json matrix.json

Inputs are the --json outputs of host/priority.py.
"""
import argparse
import json
import sys


def load_reports(files):
    for path in files:
        with open(path) as f:
            yield json.load(f)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+", metavar="REPORT")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--json", metavar="FILE", default=None)
    args = ap.parse_args()

    touched = {}
    seen = set()
    n_reports = 0

    for rep in load_reports(args.reports):
        n_reports += 1
        for e in rep.get("priority", []):
            k = (e["mod"], e["fn"])
            seen.add(k)
            t = touched.setdefault(k, {"reports": 0, "calls": 0})
            t["reports"] += 1
            t["calls"] += e.get("calls", 0)
        for e in rep.get("missing", []):
            seen.add((e["mod"], e["fn"]))
    # a function that no report touched never appears in any priority list
    for k in list(seen):
        touched.setdefault(k, {"reports": 0, "calls": 0})

    rows = [{"mod": k[0], "fn": k[1], "reports": touched[k]["reports"],
             "total": n_reports, "calls": touched[k]["calls"]}
            for k in sorted(seen, key=lambda k: (k[0], k[1]))]
    n_touched = sum(1 for r in rows if r["reports"])

    print(f"{n_reports} report(s), {len(rows)} declared functions, "
          f"{n_touched} touched at least once")
    print()
    if args.markdown:
        print("| seen in | calls | function |")
        print("|---:|---:|---|---|")
        for r in sorted(rows, key=lambda r: (-r["reports"], -r["calls"], r["mod"], r["fn"])):
            if r["reports"] == 0:
                continue
            print(f"| {r['reports']}/{r['total']} | {r['calls']} | `{r['mod']}.{r['fn']}` |")
        untouched = [r for r in rows if r["reports"] == 0]
        if untouched:
            print(f"\nNever touched in any report ({len(untouched)}):")
            for r in untouched:
                print(f"- `{r['mod']}.{r['fn']}`")
    else:
        print(f"{'reports':>7} {'calls':>8}  function")
        for r in sorted(rows, key=lambda r: (-r["reports"], -r["calls"], r["mod"], r["fn"])):
            if r["reports"] == 0:
                continue
            print(f"{r['reports']:>4}/{r['total']:<2} {r['calls']:>8}  {r['mod']}.{r['fn']}")

    if args.json:
        text = json.dumps({"reports": n_reports,
                           "declared": len(rows), "touched": n_touched,
                           "matrix": rows}, indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.json, "w") as f:
                f.write(text + "\n")
            print(f"[json] {args.json}")


if __name__ == "__main__":
    main()