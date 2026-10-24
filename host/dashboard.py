#!/usr/bin/env python3
"""dashboard.py — render a tracedb database as one static HTML page.

For each capture: a timeline of calls across the run (seq split into
buckets, stacked by module) and its hottest functions. Above them, a
capture x module matrix shows which runs depend on which libraries, the
quickest way to spot a run that pulls in a module the others never touch.

    python3 host/tracedb.py import traces.db traces/*.jsonl
    python3 host/dashboard.py traces.db -o report.html

The page is self-contained (inline SVG and CSS, no scripts or network), so
it can be attached to an issue or opened straight from disk.
"""
import argparse
import html
import os
import sys

import tracedb

PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]

CSS = """
:root { --bg:#fff; --fg:#1d1d1f; --muted:#6e6e73; --line:#e5e5ea; --cell:#4e79a7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161618; --fg:#f2f2f7; --muted:#a1a1a6; --line:#3a3a3c; --cell:#76a5d8; }
}
body { background:var(--bg); color:var(--fg); margin:0 auto; max-width:1100px;
       padding:24px 16px; font:14px/1.45 -apple-system, system-ui, sans-serif; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:32px 0 8px; }
.muted { color:var(--muted); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; font-variant-numeric:tabular-nums; }
th, td { padding:4px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th:first-child, td:first-child { text-align:left; }
.legend span { display:inline-block; margin-right:12px; }
.legend i { display:inline-block; width:10px; height:10px; margin-right:4px; border-radius:2px; }
svg { display:block; max-width:100%; height:auto; }
"""

def esc(v):
    return html.escape("" if v is None else str(v))

def timeline(db, cid, mods, colors, buckets):
    lo, hi = db.execute("SELECT min(seq), max(seq) FROM calls WHERE capture_id = ?",
                        (cid,)).fetchone()
    if lo is None:
        return "<p class=muted>no calls</p>"
    width = max(1, (hi - lo + 1 + buckets - 1) // buckets)
    grid = {}
    for b, mod, n in db.execute(
            "SELECT (seq - ?) / ?, mod, count(*) FROM calls WHERE capture_id = ? "
            "AND seq IS NOT NULL GROUP BY 1, 2", (lo, width, cid)):
        key = mod if mod in colors else "other"
        grid.setdefault(b, {}).setdefault(key, 0)
        grid[b][key] += n
    peak = max(sum(v.values()) for v in grid.values())
    w, h, bw = 960, 120, 960 / buckets
    out = [f'<svg viewBox="0 0 {w} {h + 16}" role="img" aria-label="calls over the run">']
    for b, parts in sorted(grid.items()):
        y = h
        for mod in mods + ["other"]:
            n = parts.get(mod, 0)
            if not n:
                continue
            bh = h * n / peak
            y -= bh
            out.append(f'<rect x="{b * bw:.1f}" y="{y:.1f}" width="{max(bw - 1, 1):.1f}" '
                       f'height="{bh:.1f}" fill="{colors.get(mod, "#888")}">'
                       f'<title>seq {lo + b * width}..{lo + (b + 1) * width - 1}: '
                       f'{esc(mod)} {n}</title></rect>')
    out.append(f'<text x="0" y="{h + 14}" font-size="11" fill="currentColor">seq {lo}</text>')
    out.append(f'<text x="{w}" y="{h + 14}" font-size="11" text-anchor="end" '
               f'fill="currentColor">seq {hi}</text></svg>')
    return "".join(out)

def render(db, top, buckets):
    caps = db.execute("SELECT id, pid, title, fw, calls, drops, skipped, path "
                      "FROM captures ORDER BY id").fetchall()
    mods = [m for (m,) in db.execute(
        "SELECT mod FROM calls GROUP BY mod ORDER BY count(*) DESC LIMIT ?",
        (len(PALETTE) - 1,))]
    colors = dict(zip(mods, PALETTE))
    colors["other"] = PALETTE[-1]
    all_mods = [m for (m,) in db.execute("SELECT DISTINCT mod FROM calls ORDER BY mod")]
    matrix = {}
    for cid, mod, n in db.execute("SELECT capture_id, mod, count(*) FROM calls GROUP BY 1, 2"):
        matrix[(cid, mod)] = n
    peak = max(matrix.values(), default=1)

    out = ["<!doctype html><html lang=en><head><meta charset=utf-8>",
           "<meta name=viewport content='width=device-width, initial-scale=1'>",
           f"<title>ProsperoTrace Captures</title><style>{CSS}</style></head><body>",
           "<h1>ProsperoTrace captures</h1>",
           f"<p class=muted>{len(caps)} captures, {sum(c[4] for c in caps)} calls, "
           f"{len(all_mods)} modules</p>",
           "<h2>Module dependencies</h2><div class=scroll><table><tr><th>capture</th>"]
    out += [f"<th>{esc(m)}</th>" for m in all_mods]
    out.append("</tr>")
    for c in caps:
        out.append(f"<tr><td>#{c[0]} {esc(c[2])} <span class=muted>fw {esc(c[3])}</span></td>")
        for m in all_mods:
            n = matrix.get((c[0], m), 0)
            alpha = 0 if not n else 0.15 + 0.85 * n / peak
            out.append(f"<td style='background:color-mix(in srgb, var(--cell) "
                       f"{alpha * 100:.0f}%, transparent)'>{n or ''}</td>")
        out.append("</tr>")
    out.append("</table></div>")

    out.append("<div class=legend>")
    out += [f"<span><i style='background:{colors[m]}'></i>{esc(m)}</span>"
            for m in mods + ["other"]]
    out.append("</div>")
    for c in caps:
        cid, pid, title, fw, calls, drops, skipped, path = c
        warn = f", <b>{drops} dropped</b>" if drops else ""
        out.append(f"<h2>#{cid} {esc(title)} <span class=muted>pid {esc(pid)}, fw {esc(fw)}, "
                   f"{calls} calls{warn}</span></h2>")
        out.append(f"<p class=muted>{esc(os.path.basename(path))}"
                   f"{f', {skipped} malformed lines skipped' if skipped else ''}</p>")
        out.append(timeline(db, cid, mods, colors, buckets))
        out.append("<div class=scroll><table><tr><th>function</th><th>calls</th>"
                   "<th>first seq</th></tr>")
        for mod, fn, n, first in db.execute(
                "SELECT mod, fn, calls, first_seq FROM functions WHERE capture_id = ? "
                "ORDER BY calls DESC, mod, fn LIMIT ?", (cid, top)):
            out.append(f"<tr><td>{esc(mod)}.{esc(fn)}</td><td>{n}</td><td>{esc(first)}</td></tr>")
        out.append("</table></div>")
    out.append("</body></html>")
    return "\n".join(out)

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", help="database written by tracedb.py import")
    ap.add_argument("-o", "--out", default="report.html", help="output HTML file (- for stdout)")
    ap.add_argument("--top", type=int, default=15, help="functions listed per capture")
    ap.add_argument("--buckets", type=int, default=80, help="timeline columns per capture")
    args = ap.parse_args()
    page = render(tracedb.open_ro(args.db), args.top, max(1, args.buckets))
    if args.out == "-":
        sys.stdout.write(page + "\n")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(page + "\n")
        print(f"[html] {args.out}")

if __name__ == "__main__":
    main()
