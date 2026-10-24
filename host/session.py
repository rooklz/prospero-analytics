#!/usr/bin/env python3
"""session.py — one tracing session, end to end on the host.

Runs the receiver, waits for the agent's captures, then validates each one
against EVENT_FORMAT.md, imports it into a tracedb database and renders the
dashboard. Start it, then launch the agent on the console (ProsperoTrace's
deploy.sh, or tools/fixture.sh which does the same for the fixture):

    python3 host/session.py --out session/ --captures 1 --timeout 120

Leaves session/traces/*.jsonl, session/traces.db, session/report.html and
prints a summary. --baseline FILE also diffs each capture's API surface
against FILE (tracediff --normalize) and fails if a function surfaced or
went away. Exit 0 on success, 1 on a format or surface failure, 2 when no
capture arrived.
"""
import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

def tool(name, *args, **kw):
    return subprocess.run([sys.executable, os.path.join(HERE, name), *args], **kw)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="session", help="session directory")
    ap.add_argument("--port", type=int, default=9029)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--captures", type=int, default=1, help="stop after this many connections closed")
    ap.add_argument("--timeout", type=float, default=120, help="seconds to wait for them")
    ap.add_argument("--baseline", help="capture to diff each new one against")
    args = ap.parse_args()

    traces = os.path.join(args.out, "traces")
    os.makedirs(traces, exist_ok=True)
    before = set(glob.glob(os.path.join(traces, "*.jsonl")))
    rx = subprocess.Popen([sys.executable, os.path.join(HERE, "receiver.py"), "--bind", args.bind,
                           "--port", str(args.port), "--out", traces, "-q"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    banner = rx.stdout.readline()
    if not banner.startswith("[*] listening"):
        rx.wait()
        print(f"session: receiver did not start:\n{banner}{rx.stdout.read()}", file=sys.stderr)
        return 2
    print(banner.rstrip(), flush=True)
    closed = []
    def collect():
        for line in rx.stdout:
            if line.startswith("[-]"):
                closed.append(line.rstrip())
    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline and len(closed) < args.captures and rx.poll() is None:
            time.sleep(0.2)
    finally:
        rx.send_signal(signal.SIGINT)
        try:
            rx.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rx.kill()

    new = sorted(set(glob.glob(os.path.join(traces, "*.jsonl"))) - before)
    if not new:
        print("session: no capture arrived", file=sys.stderr)
        return 2

    rc = 0
    if tool("validate.py", *new).returncode != 0:
        rc = 1
    db = os.path.join(args.out, "traces.db")
    tool("tracedb.py", "import", db, *new, check=False)
    tool("dashboard.py", db, "-o", os.path.join(args.out, "report.html"), check=False)
    if args.baseline:
        for path in new:
            out = os.path.join(args.out, os.path.basename(path) + ".diff.json")
            tool("tracediff.py", args.baseline, path, "--normalize", "--json", out,
                 stdout=subprocess.DEVNULL)
            with open(out) as f:
                d = json.load(f)
            moved = [f"+{e['mod']}.{e['fn']}" for e in d["surfaced"]] + \
                    [f"-{e['mod']}.{e['fn']}" for e in d["gone"]]
            if moved:
                print(f"session: {os.path.basename(path)} API surface changed: {' '.join(moved)}")
                rc = 1
            else:
                print(f"session: {os.path.basename(path)} API surface matches the baseline")
    print(f"session: {len(new)} capture(s), database {db}, report {os.path.join(args.out, 'report.html')}")
    return rc

if __name__ == "__main__":
    sys.exit(main())
