#!/usr/bin/env python3
"""catalogue.py — keep a reusable corpus of captures.

A catalogue is a tracedb database whose captures table you treat as the
source of truth for a set of runs: import files (idempotent, same SHA-256),
list them with filters, and export a subset (files + an index.json) for a
report or a comparison run.

    python3 host/catalogue.py import corpus.db traces/*.jsonl
    python3 host/catalogue.py list corpus.db --fw 13.40
    python3 host/catalogue.py export corpus.db --title echo --out subset/

Uses the tracedb schema and import logic; add nothing that would conflict
with `tracedb.py` commands run on the same database.
"""
import argparse
import datetime
import json
import os
import shutil
import sys

import tracedb
from tracedb import emit, import_capture, open_ro, open_rw


def _filters(args):
    where, params = [], []
    if args.title:
        where.append("title = ?")
        params.append(args.title)
    if args.fw:
        where.append("fw = ?")
        params.append(args.fw)
    if args.since:
        where.append("imported_at >= ?")
        params.append(args.since)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def cmd_import(args):
    db = open_rw(args.db)
    failed = 0
    added = 0
    for path in args.files:
        try:
            status, cid, stats = import_capture(db, path)
        except OSError as e:
            print(f"  ! {path}: {e.strerror}", file=sys.stderr)
            failed += 1
            continue
        if stats is None:
            print(f"  = {path}: already in the catalogue (capture {cid})")
            continue
        print(f"  {'~' if status == 'replaced' else '+'} {path}: capture {cid}, "
              f"{stats['events']} events, {stats['calls']} calls, {stats['drops']} dropped")
        added += 1
    total = db.execute("SELECT count(*), coalesce(sum(events),0), coalesce(sum(calls),0) "
                       "FROM captures").fetchone()
    print(f"{args.db}: {total[0]} captures, {total[1]} events, {total[2]} calls "
          f"({added} added this run)")
    if failed:
        sys.exit(1)


def cmd_list(args):
    db = open_ro(args.db)
    where, params = _filters(args)
    cols = ["id", "title", "fw", "events", "calls", "drops", "imported_at", "path"]
    rows = db.execute(f"SELECT {', '.join(cols)} FROM captures{where} "
                      "ORDER BY imported_at, id", params).fetchall()
    emit(args, cols, rows)
    if args.json != "-":
        print(f"{len(rows)} capture(s)")


def cmd_export(args):
    db = open_ro(args.db)
    where, params = _filters(args)
    cols = ["id", "path", "sha256", "pid", "title", "fw", "events", "calls",
            "drops", "imported_at"]
    rows = db.execute(
        f"SELECT {', '.join(cols)} FROM captures{where} ORDER BY imported_at, id",
        params).fetchall()
    if not rows:
        print("catalogue: nothing matches the filters", file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    entries = []
    for row in rows:
        rec = dict(zip(cols, row))
        dst_name = f"{rec['id']}-{os.path.basename(rec['path'])}"
        shutil.copyfile(rec["path"], os.path.join(args.out, dst_name))
        rec["exported_as"] = dst_name
        entries.append(rec)
    index = {"exported_at": datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds"), "entries": entries}
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, indent=2)
    print(f"catalogue: {len(entries)} capture(s) -> {args.out}/ (index.json written)")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="add captures to the catalogue")
    p.add_argument("db")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("list", help="list captures with filters")
    p.add_argument("db")
    p.add_argument("--title")
    p.add_argument("--fw")
    p.add_argument("--since", metavar="ISO", help="imported_at >= this (e.g. 2026-10-01)")
    p.add_argument("--json", metavar="FILE", default=None,
                   help="also write rows as JSON (use - for stdout only)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("export", help="copy matching captures out with an index.json")
    p.add_argument("db")
    p.add_argument("--title")
    p.add_argument("--fw")
    p.add_argument("--since", metavar="ISO")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_export)

    args = ap.parse_args()
    try:
        rc = args.func(args)
    except Exception as e:
        sys.exit(f"catalogue: {e}")
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()