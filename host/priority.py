#!/usr/bin/env python3
"""priority.py — coverage and implementation-backlog ordering from captures.

Freestanding version of the tracedb reports that works directly on capture
files plus a manifest of declared functions (`module function nid` lines,
the same format as the agent's nids.txt and compatible with a library
re-implementation project's declarations).

    python3 host/priority.py traces/*.jsonl --manifest nids.txt
    python3 host/priority.py a.jsonl b.jsonl --manifest nids.txt --markdown
    python3 host/priority.py a.jsonl --manifest nids.txt --missing --json -

Reads one or more captures (a multi-connection file is treated as one
capture). Reports, per declared function: coverage, rank by calls then by
distinct captures using it, argument and return sketches. `--missing` lists
declared functions the corpus never exercised. --json writes the full
structured report (used by coveragemap.py).
"""
import argparse
import collections
import json
import sys

import tracefile
import tracedb


def _hex_int(v):
    try:
        return int(v, 16)
    except (TypeError, ValueError):
        return None


def sketch_counts(vals):
    """Return {distinct, min, max, top} for a slot's value collection."""
    counter = collections.Counter(vals)
    nums = [n for n in (_hex_int(v) for v in counter) if n is not None]
    top = [{"v": v, "n": n} for v, n in counter.most_common(3)]
    return {"distinct": len(counter),
            "min": hex(min(nums)) if nums else None,
            "max": hex(max(nums)) if nums else None,
            "top": top}


def summarize(path, per_fn, counts, drop_total):
    """Walk one capture, accumulate per-function sketches and totals."""
    seen = set()
    for ev in tracefile.events(path):
        t = ev.get("type")
        if t == "call":
            fn = (ev.get("mod", "?"), ev.get("fn", "?"))
            counts["calls"] += 1
            seen.add(fn)
            s = per_fn.setdefault(fn, {"calls": 0, "captures": set(), "tid": set(),
                                       "slots": [collections.Counter()
                                                 for _ in range(7)]})
            s["calls"] += 1
            if isinstance(ev.get("tid"), int):
                s["tid"].add(ev["tid"])
            for i, v in enumerate(ev.get("args", [])[:6]):
                if isinstance(v, str):
                    s["slots"][i][v] += 1
            if isinstance(ev.get("ret"), str):
                s["slots"][6][ev["ret"]] += 1
        elif t == "drops":
            drop_total[0] += ev.get("n", 0)
    return seen


def build(captures):
    per_fn = {}
    counts = {"calls": 0}
    drop_total = [0]
    fn_captures = collections.Counter()
    for path in captures:
        seen = summarize(path, per_fn, counts, drop_total)
        for fn in seen:
            fn_captures[fn] += 1
    return per_fn, fn_captures, counts, drop_total[0]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", nargs="+", metavar="CAPTURE")
    ap.add_argument("--manifest", required=True,
                    help="declared functions (module function nid lines)")
    ap.add_argument("--top", type=int, default=50, metavar="N")
    ap.add_argument("--missing", action="store_true",
                    help="show only the declared-but-unseen functions")
    ap.add_argument("--markdown", action="store_true",
                    help="emit the priority table as Markdown")
    ap.add_argument("--json", metavar="FILE", default=None,
                    help="also write the structured report (use - for stdout only)")
    args = ap.parse_args()

    per_fn, fn_captures, counts, drops = build(args.captures)
    declared = tracedb.load_nids(args.manifest)
    declared_set = set(declared)
    seen_set = set(fn_captures)
    touched_set = seen_set & declared_set

    per_module = collections.defaultdict(lambda: [0, 0, 0])
    for mod, fn in declared:
        per_module[mod][0] += 1
        if (mod, fn) in touched_set:
            per_module[mod][1] += 1
            per_module[mod][2] += per_fn[(mod, fn)]["calls"]

    priority = []
    for fn in touched_set:
        s = per_fn[fn]
        priority.append({
            "mod": fn[0], "fn": fn[1],
            "calls": s["calls"],
            "captures": fn_captures[fn],
            "threads": len(s["tid"]),
            "arg": [sketch_counts(c) for c in s["slots"][:6]],
            "ret": sketch_counts(s["slots"][6]),
        })
    priority.sort(key=lambda e: (-e["captures"], -e["calls"], e["mod"], e["fn"]))

    missing = sorted(declared_set - touched_set)

    if args.json != "-":
        print(f"{len(args.captures)} capture(s), {counts['calls']} calls, {drops} dropped")
        total_decl = len(declared_set)
        print(f"declared {total_decl}, touched {len(touched_set)}, "
              f"coverage {100 * len(touched_set) / total_decl:.1f}%")
        print()
        print(f"{'module':<22} {'declared':>8} {'touched':>8} {'pct':>6} {'calls':>8}")
        for mod, (d, t, c) in sorted(per_module.items()):
            print(f"{mod:<22} {d:>8} {t:>8} {100 * t / d:>5.1f}% {c:>8}")
        print()

    if args.missing:
        print(f"untouched (declared, never seen): {len(missing)}")
        for mod, fn in missing:
            print(f"  - {mod}.{fn}")
        if args.json:
            _write_json(args.json, _report(args, counts, drops, per_module,
                                           touched_set, declared_set, priority, missing))
        return

    if args.markdown:
        print(f"priority backlog: {len(priority)} declared-and-touched functions\n")
        print("| in | calls | function |")
        print("|---:|---:|---|---|")
        for e in priority[:args.top]:
            print(f"| {e['captures']} | {e['calls']} | `{e['mod']}.{e['fn']}` |")
        if missing:
            print("\nNever touched by this corpus:")
            for mod, fn in missing:
                print(f"- `{mod}.{fn}`")
    else:
        print(f"priority backlog: {len(priority)} declared-and-touched functions")
        print(f"{'in':>4} {'calls':>7}  function")
        for e in priority[:args.top]:
            print(f"{e['captures']:>4} {e['calls']:>7}  {e['mod']}.{e['fn']}")

    if args.json:
        _write_json(args.json, _report(args, counts, drops, per_module,
                                       touched_set, declared_set, priority, missing))


def _report(args, counts, drops, per_module, touched_set, declared_set, priority, missing):
    return {
        "inputs": {"captures": len(args.captures), "calls": counts["calls"],
                   "drops": drops},
        "coverage": {
            "overall": {"declared": len(declared_set), "touched": len(touched_set)},
            "modules": {mod: {"declared": d, "touched": t, "calls": c}
                        for mod, (d, t, c) in per_module.items()},
        },
        "priority": priority,
        "missing": [{"mod": m, "fn": f} for m, f in missing],
    }


def _write_json(path, obj):
    text = json.dumps(obj, indent=2)
    if path == "-":
        sys.stdout.write(text + "\n")
    else:
        with open(path, "w") as f:
            f.write(text + "\n")
        print(f"[json] {path}")


if __name__ == "__main__":
    main()