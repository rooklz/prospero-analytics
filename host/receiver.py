#!/usr/bin/env python3
"""receiver.py — capture a ProsperoTrace event stream to JSONL.

The agent connects out to this receiver, so the console never needs to run a
server for tracing. Each attached target gets its own output file:

    traces/trace-<pid>-<unixts>.jsonl

Live filters reduce console->host traffic client-side only for display; the
file always gets the full stream. Use the agent-side filters for bandwidth.

If a target reconnects within the same second, the new file gets a -<n>
suffix instead of being appended to the previous one.

Ctrl+C closes all files and prints a per-target summary.
"""
import argparse
import os
import signal
import socket
import sys
import threading
import time

import tracefile

MAX_LINE = 1 << 20     # an event is ~300 bytes; anything longer is a broken peer

class Target:
    def __init__(self, sock, addr, outdir, show, inc_mod, exc_mod, match):
        self.sock = sock
        self.addr = addr
        self.path = None
        self.fh = None
        self.pid = None
        self.count = 0
        self.drops = 0
        self.show = show
        self.inc_mod = inc_mod
        self.exc_mod = exc_mod
        self.match = match
        self.outdir = outdir
        self.lock = threading.Lock()

    def open_file(self, hello):
        self.pid = hello.get("pid", "unknown")
        # the pid ends up in a path; never let the peer pick the directory
        tag = str(self.pid) if isinstance(self.pid, int) else "unknown"
        stem = os.path.join(self.outdir, f"trace-{tag}-{int(time.time())}")
        for n in range(1000):
            self.path = f"{stem}.jsonl" if n == 0 else f"{stem}-{n}.jsonl"
            try:
                self.fh = open(self.path, "x", encoding="utf-8", buffering=1)
                break
            except FileExistsError:
                continue
        else:
            raise OSError(f"no free file name for {stem}.jsonl")
        title = hello.get("title", "?")
        fw = hello.get("fw", "?")
        print(f"[+] {self.addr[0]}:{self.addr[1]} -> pid {self.pid} ({title}, fw {fw}) => {self.path}")

    def visible(self, ev):
        if ev.get("type") != "call":
            return True
        mod = ev.get("mod", "")
        fn = ev.get("fn", "")
        if self.inc_mod and mod not in self.inc_mod:
            return False
        if mod in self.exc_mod:
            return False
        if self.match and self.match not in fn:
            return False
        return True

    def handle(self, line):
        ev = tracefile.parse(line)
        if ev is None:
            print(f"[!] bad line from {self.addr[0]}: {line[:80]!r}")
            return
        if self.fh is None:
            if ev.get("type") != "hello":
                return  # wait for hello before creating the file
            self.open_file(ev)
        with self.lock:
            self.fh.write(line + "\n")
        if ev.get("type") == "call":
            self.count += 1
        elif ev.get("type") == "drops":
            self.drops += ev.get("n", 0)
            if self.show:
                print(f"  {'':>8} dropped {ev.get('n', 0)}")
        if self.show and ev.get("type") == "call" and self.visible(ev):
            slim = {k: v for k, v in ev.items() if k in ("mod", "fn", "args", "ret", "tid")}
            print(f"  {self.count:>8} {slim}")

    def run(self):
        buf = b""
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    if raw:
                        self.handle(raw.decode("utf-8", "replace"))
                if len(buf) > MAX_LINE:
                    print(f"[!] {self.addr[0]}: line over {MAX_LINE} bytes, discarding it")
                    buf = b""
        except OSError:
            pass
        finally:
            if self.fh:
                self.fh.close()
            print(f"[-] {self.addr[0]}:{self.addr[1]} closed "
                  f"({self.count} calls, {self.drops} dropped)")

    def stop(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9029, help="TCP port (0 picks a free one)")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--out", default="traces", help="output directory")
    ap.add_argument("--include-module", action="append", default=[])
    ap.add_argument("--exclude-module", action="append", default=[])
    ap.add_argument("--match", default="", help="function-name substring filter (display only)")
    ap.add_argument("-q", "--quiet", action="store_true", help="record only, no live display")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # live through pipes and tee

    os.makedirs(args.out, exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, args.port))
    srv.listen(8)
    port = srv.getsockname()[1]
    print(f"[*] listening on {args.bind}:{port}, writing to {args.out}/", flush=True)

    stop = threading.Event()
    def on_sigint(_sig, _frm):
        stop.set()
        srv.close()
        print("\n[*] stopping")
    signal.signal(signal.SIGINT, on_sigint)

    live = []
    while not stop.is_set():
        try:
            sock, addr = srv.accept()
        except OSError:
            break
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        t = Target(sock, addr, args.out, not args.quiet,
                   set(args.include_module), set(args.exclude_module), args.match)
        th = threading.Thread(target=t.run, daemon=True)
        th.start()
        live = [(t2, th2) for t2, th2 in live if th2.is_alive()] + [(t, th)]

    # wake every reader so each one closes its file and prints its summary
    for t, _ in live:
        t.stop()
    for _, th in live:
        th.join(timeout=2)

if __name__ == "__main__":
    main()
