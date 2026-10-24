#!/usr/bin/env python3
"""tracedb.py — import ProsperoTrace captures into SQLite and query them.

One database holds many captures, so questions that span runs become a
single query instead of a chain of pairwise diffs:

  which captures call sceKernelMmap, and how often?
  which functions does the whole corpus touch, and in how many runs?
  what did the fw 14.10 runs call that the 13.40 runs never did?

    python3 host/tracedb.py import traces.db traces/*.jsonl
    python3 host/tracedb.py captures traces.db
    python3 host/tracedb.py functions traces.db --top 30
    python3 host/tracedb.py who traces.db 'sceKernel*'
    python3 host/tracedb.py sql traces.db "SELECT fw, count(*) FROM captures GROUP BY fw"

Import is idempotent: a file whose contents are already stored (same
SHA-256) is skipped, and a file that changed since it was imported (a
capture that was still being written) replaces its earlier rows. Malformed
lines are skipped and counted per capture.

Tables: captures (one row per file, from its hello record), calls (one row
per call event, args as a0..a5 hex text), drops, and the view functions
(per-capture call counts). Every query command opens the database
read-only; `--json FILE` writes the rows as a list of objects.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sqlite3
import sys

import tracefile

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL,
    sha256      TEXT NOT NULL UNIQUE,
    pid         INTEGER,
    title       TEXT,
    fw          TEXT,
    calls       INTEGER NOT NULL,
    drops       INTEGER NOT NULL,
    skipped     INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS captures_by_path ON captures(path);
CREATE TABLE IF NOT EXISTS calls (
    capture_id INTEGER NOT NULL REFERENCES captures(id),
    seq INTEGER, ts INTEGER, tid INTEGER,
    mod TEXT NOT NULL, fn TEXT NOT NULL, nid TEXT,
    a0 TEXT, a1 TEXT, a2 TEXT, a3 TEXT, a4 TEXT, a5 TEXT,
    ret TEXT
);
CREATE INDEX IF NOT EXISTS calls_by_fn ON calls(fn, mod);
CREATE INDEX IF NOT EXISTS calls_by_capture ON calls(capture_id, seq);
CREATE TABLE IF NOT EXISTS drops (
    capture_id INTEGER NOT NULL REFERENCES captures(id),
    seq INTEGER,
    n   INTEGER NOT NULL
);
CREATE VIEW IF NOT EXISTS functions AS
    SELECT capture_id, mod, fn, count(*) AS calls, min(seq) AS first_seq
    FROM calls GROUP BY capture_id, mod, fn;
"""

def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None

def _str(v):
    return v if isinstance(v, str) else None

def _lines(path, size):
    # stop at the size measured up front so the hash and the rows describe
    # the same bytes even if the receiver is still appending to the file
    with open(path, "rb") as f:
        left = size
        for raw in f:
            if left <= 0:
                break
            raw = raw[:left]
            left -= len(raw)
            yield raw

def open_rw(path):
    db = sqlite3.connect(path)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        sys.exit(f"tracedb: {path} has schema v{version}; this tool knows v{SCHEMA_VERSION}")
    db.executescript(SCHEMA)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return db

def open_ro(path):
    if not os.path.isfile(path):
        sys.exit(f"tracedb: no database at {path} (create one with: tracedb.py import {path} FILES)")
    return sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True)

def import_capture(db, path):
    """Import one file. Returns (status, capture_id, stats)."""
    path = os.path.abspath(path)
    size = os.path.getsize(path)
    h = hashlib.sha256()
    for raw in _lines(path, size):
        h.update(raw)
    digest = h.hexdigest()

    row = db.execute("SELECT id FROM captures WHERE sha256 = ?", (digest,)).fetchone()
    if row:
        return "unchanged", row[0], None
    old = db.execute("SELECT id FROM captures WHERE path = ?", (path,)).fetchall()

    stats = {"calls": 0, "drops": 0, "skipped": 0, "hellos": 0}
    hello = {}
    drops = []

    def calls(cid):
        for raw in _lines(path, size):
            ev = tracefile.parse(raw.decode("utf-8", "replace"))
            if ev is None:
                if raw.strip():
                    stats["skipped"] += 1
                continue
            t = ev.get("type")
            if t == "call":
                args = ev.get("args")
                args = [_str(a) for a in args[:6]] if isinstance(args, list) else []
                args += [None] * (6 - len(args))
                stats["calls"] += 1
                yield (cid, ev.get("seq"), _int(ev.get("ts")), _int(ev.get("tid")),
                       ev.get("mod", "?"), ev.get("fn", "?"), _str(ev.get("nid")),
                       *args, _str(ev.get("ret")))
            elif t == "drops":
                drops.append((cid, ev.get("seq"), ev.get("n", 0)))
                stats["drops"] += ev.get("n", 0)
            elif t == "hello":
                stats["hellos"] += 1
                if not hello:
                    hello.update(ev)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with db:
        for (oid,) in old:
            for table, col in (("calls", "capture_id"), ("drops", "capture_id"), ("captures", "id")):
                db.execute(f"DELETE FROM {table} WHERE {col} = ?", (oid,))
        cid = db.execute(
            "INSERT INTO captures (path, sha256, calls, drops, skipped, imported_at) "
            "VALUES (?, ?, 0, 0, 0, ?)", (path, digest, now)).lastrowid
        db.executemany("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", calls(cid))
        db.executemany("INSERT INTO drops VALUES (?,?,?)", drops)
        db.execute(
            "UPDATE captures SET pid = ?, title = ?, fw = ?, calls = ?, drops = ?, skipped = ? "
            "WHERE id = ?",
            (_int(hello.get("pid")), _str(hello.get("title")), _str(hello.get("fw")),
             stats["calls"], stats["drops"], stats["skipped"], cid))
    return ("replaced" if old else "imported"), cid, stats

def emit(args, cols, rows):
    """Print rows as an aligned table, and as JSON when --json is given."""
    if args.json != "-":
        cells = [[("" if v is None else str(v)) for v in r] for r in rows]
        widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
        print("  ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip())
        for r in cells:
            print("  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip())
    if args.json:
        text = json.dumps([dict(zip(cols, r)) for r in rows], indent=2)
        if args.json == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.json, "w") as f:
                f.write(text + "\n")
            print(f"[json] {args.json}")

def cmd_import(args):
    db = open_rw(args.db)
    failed = 0
    for path in args.files:
        try:
            status, cid, stats = import_capture(db, path)
        except OSError as e:
            print(f"  ! {path}: {e.strerror}", file=sys.stderr)
            failed += 1
            continue
        if stats is None:
            print(f"  = {path}: already imported as capture {cid}")
            continue
        note = f", {stats['skipped']} malformed lines skipped" if stats["skipped"] else ""
        print(f"  {'~' if status == 'replaced' else '+'} {path}: capture {cid}, "
              f"{stats['calls']} calls, {stats['drops']} dropped{note}"
              f"{' (replaced earlier import)' if status == 'replaced' else ''}")
        if stats["hellos"] > 1:
            print(f"    note: {stats['hellos']} hello records; the file holds more than one "
                  "connection and is imported as one capture", file=sys.stderr)
    total = db.execute("SELECT count(*), coalesce(sum(calls), 0) FROM captures").fetchone()
    print(f"{args.db}: {total[0]} captures, {total[1]} calls")
    if failed:
        sys.exit(1)

def cmd_captures(args):
    db = open_ro(args.db)
    cols = ["id", "pid", "title", "fw", "calls", "drops", "skipped", "path"]
    rows = db.execute(f"SELECT {', '.join(cols)} FROM captures ORDER BY id").fetchall()
    emit(args, cols, rows)

def _capture_filter(ids):
    if not ids:
        return "", []
    return f"WHERE capture_id IN ({','.join('?' * len(ids))})", list(ids)

def cmd_functions(args):
    db = open_ro(args.db)
    where, params = _capture_filter(args.capture)
    cols = ["calls", "captures", "mod", "fn"]
    rows = db.execute(
        f"SELECT count(*), count(DISTINCT capture_id), mod, fn FROM calls {where} "
        "GROUP BY mod, fn ORDER BY count(*) DESC, mod, fn LIMIT ?",
        params + [args.top]).fetchall()
    emit(args, cols, rows)

def cmd_who(args):
    db = open_ro(args.db)
    # a dotted name or pattern matches mod.fn, anything else matches fn alone
    target = "(k.mod || '.' || k.fn)" if "." in args.name else "k.fn"
    cols = ["capture", "title", "fw", "mod", "fn", "calls", "first_seq"]
    rows = db.execute(
        f"SELECT c.id, c.title, c.fw, k.mod, k.fn, count(*), min(k.seq) "
        f"FROM calls k JOIN captures c ON c.id = k.capture_id WHERE {target} GLOB ? "
        "GROUP BY c.id, k.mod, k.fn ORDER BY c.id, count(*) DESC, k.mod, k.fn",
        (args.name,)).fetchall()
    emit(args, cols, rows)

def cmd_sql(args):
    db = open_ro(args.db)
    try:
        cur = db.execute(args.query)
    except sqlite3.Error as e:
        sys.exit(f"tracedb: {e}")
    cols = [d[0] for d in cur.description or []]
    emit(args, cols, cur.fetchall())

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="add capture files to a database (created if missing)")
    p.add_argument("db")
    p.add_argument("files", nargs="+", help="trace-*.jsonl captures")
    p.set_defaults(func=cmd_import)

    def query(name, func, desc):
        p = sub.add_parser(name, help=desc)
        p.add_argument("db")
        p.add_argument("--json", metavar="FILE", default=None,
                       help="also write the rows as JSON (use - for stdout only)")
        p.set_defaults(func=func)
        return p

    query("captures", cmd_captures, "list imported captures with their hello metadata")
    p = query("functions", cmd_functions,
              "call counts per function across captures, and how many captures call it")
    p.add_argument("--capture", type=int, action="append", default=[], metavar="ID",
                   help="only these captures (repeatable)")
    p.add_argument("--top", type=int, default=50)
    p = query("who", cmd_who, "which captures call a function, and how often")
    p.add_argument("name", help="fn or mod.fn; shell-style * ? [..] patterns allowed")
    p = query("sql", cmd_sql, "run a read-only SQL query against the database")
    p.add_argument("query")

    args = ap.parse_args()
    try:
        args.func(args)
    except sqlite3.DatabaseError as e:
        sys.exit(f"tracedb: {args.db}: {e}")

if __name__ == "__main__":
    main()
