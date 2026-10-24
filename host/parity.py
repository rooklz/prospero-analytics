#!/usr/bin/env python3
"""parity.py — compare a console capture against a desktop capture.

The desktop side is the same title relinked through a compatibility layer
and traced in a compatible JSONL shape (same stable `call` keys as
EVENT_FORMAT.md). The output is the worklist for the layer:

    missing   called on the console, absent on the desktop  -> implement
    extra     called on the desktop, absent on the console  -> inspect
    drifted   on both, but rate or argument shape differs
    matches   on both, comparable rates

Rates are per 1000 calls so captures of different lengths compare fairly.

    python3 host/parity.py console.jsonl desktop.jsonl
    python3 host/parity.py console.jsonl desktop.jsonl --json report.json
"""
import argparse
import collections
import json
import sys

import tracefile
import tracediff


def _rates(counts, total_calls):
    return {k: 1e3 * n / total_calls for k, n in counts.items()} if total_calls else {}


def _sketch(evgen):
    """Argument-shape fingerprint per function for one side."""
    per_fn = {}
    for ev in evgen:
        if ev.get("type") != "call":
            continue
        fn = (ev.get("mod", "?"), ev.get("fn", "?"))
        s = per_fn.setdefault(fn, {"arg": {}, "ret": collections.Counter()})
        for i, v in enumerate(ev.get("args", [])[:6]):
            if isinstance(v, str):
                s["arg"].setdefault(i, collections.Counter())[v] += 1
        if isinstance(ev.get("ret"), str):
            s["ret"][ev["ret"]] += 1
    return per_fn


def _shape_match(sk, fn):
    """True when the argument shapes on both sides look the same."""
    if fn not in sk[0] or fn not in sk[1]:
        return False
    a, b = sk[0][fn], sk[1][fn]
    return set(a["arg"].keys()) == set(b["arg"].keys()) and \
        all(set(a["arg"][i]) == set(b["arg"][i])
            for i in set(a["arg"]) | set(b["arg"])) and \
        set(a.get("ret", {})) == set(b.get("ret", {}))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("console", help="capture from the console")
    ap.add_argument("desktop", help="capture from the compatibility layer")
    ap.add_argument("--drift", type=float, default=1.0,
                    help="rate delta (per 1000 calls) that counts as drift")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json", metavar="FILE", default=None,
                    help="also write the structured report (use - for stdout only)")
    args = ap.parse_args()

    c_counts, _, c_tot = tracediff.load(args.console)
    d_counts, _, d_tot = tracediff.load(args.desktop)
    c_rate = _rates(c_counts, c_tot["calls"])
    d_rate = _rates(d_counts, d_tot["calls"])

    sk = (_sketch(tracefile.events(args.console)),
          _sketch(tracefile.events(args.desktop)))

    keys = set(c_counts) | set(d_counts)
    missing, extra, drifted, matches = [], [], [], []
    for k in sorted(keys, key=lambda k: (k[0], k[1])):
        if k in c_counts and k not in d_counts:
            missing.append({"mod": k[0], "fn": k[1]})
        elif k not in c_counts and k in d_counts:
            extra.append({"mod": k[0], "fn": k[1]})
        elif abs(c_rate[k] - d_rate[k]) >= args.drift or not _shape_match(sk, k):
            drifted.append({"mod": k[0], "fn": k[1],
                            "rate": [round(c_rate[k], 1), round(d_rate[k], 1)],
                            "shape_matches": _shape_match(sk, k)})
        else:
            matches.append({"mod": k[0], "fn": k[1]})

    print(f"console: {c_tot['calls']} calls ({len(c_counts)} fns, {c_tot['drops']} dropped)")
    print(f"desktop: {d_tot['calls']} calls ({len(d_counts)} fns, {d_tot['drops']} dropped)")

    def show(title, items, fmt):
        print(f"\n{title}: {len(items)}")
        for e in items[:args.top]:
            print("  " + fmt(e))

    show("missing (implement in the compatibility layer)", missing,
         lambda e: f"- {e['mod']}.{e['fn']}")
    show("extra (desktop calls the console never made)", extra,
         lambda e: f"+ {e['mod']}.{e['fn']}")
    show("drifted (rate or argument shape differs)", drifted,
         lambda e: f"{e['mod']}.{e['fn']}  {e['rate'][0]:>7}/1k -> {e['rate'][1]:<7}/1k  "
                   f"shape={'same' if e['shape_matches'] else 'diff'}")
    show("matches", matches, lambda e: f"= {e['mod']}.{e['fn']}")

    if args.json:
        report = {
            "console": {"calls": c_tot["calls"], "functions": len(c_counts),
                        "drops": c_tot["drops"]},
            "desktop": {"calls": d_tot["calls"], "functions": len(d_counts),
                        "drops": d_tot["drops"]},
            "missing": missing, "extra": extra, "drifted": drifted, "matches": matches,
        }
        text = json.dumps(report, indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.json, "w") as f:
                f.write(text + "\n")
            print(f"[json] {args.json}")


if __name__ == "__main__":
    main()