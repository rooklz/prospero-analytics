#!/usr/bin/env python3
"""receiver_smoke.py — drive host/receiver.py over loopback.

Checks that a target which reconnects in the same second gets its own file,
that a malformed drops record does not end the capture, that the hello pid
cannot steer the output path, and that Ctrl+C summarizes live targets.
"""
import glob
import json
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def hello(pid):
    return json.dumps({"type": "hello", "pid": pid, "title": "demo", "fw": "13.40", "seq": 0})

def call(seq, fn):
    return json.dumps({"type": "call", "seq": seq, "mod": "libkernel", "fn": fn,
                       "args": ["0x0"] * 6, "ret": "0x0"})

def wait_for(pred, what):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.05)
    fail(f"timed out waiting for {what}")

def lines(path):
    with open(path, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l]

def main():
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, "out")
        os.makedirs(out)
        # occupy the plain names a pid-7 capture could get in the next seconds
        now = int(time.time())
        for ts in range(now, now + 10):
            open(os.path.join(out, f"trace-7-{ts}.jsonl"), "w").close()
        taken = set(glob.glob(os.path.join(out, "*")))

        rx = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "host", "receiver.py"),
             "--bind", "127.0.0.1", "--port", "0", "--out", out, "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            if not select.select([rx.stdout], [], [], 5)[0]:
                fail("receiver printed no listening banner")
            banner = rx.stdout.readline()
            try:
                port = int(banner.split(":")[1].split(",")[0])
            except (IndexError, ValueError):
                fail(f"unexpected banner: {banner!r}")
            if port == 0:
                fail("banner reports port 0 instead of the bound port")

            streams = {
                "first": [hello(7), call(1, "sceKernelOpen")],
                "again": [hello(7), call(1, "sceKernelClose")],
                "drops": [hello(8), json.dumps({"type": "drops", "seq": 1, "n": "many"}),
                          call(2, "sceKernelRead")],
                "escape": [hello("../../escape"), call(1, "sceKernelWrite")],
            }
            socks = []
            for name, evs in streams.items():
                s = socket.create_connection(("127.0.0.1", port))
                s.sendall("".join(e + "\n" for e in evs).encode())
                socks.append(s)

            def captures():
                return sorted(set(glob.glob(os.path.join(out, "*"))) - taken)
            wait_for(lambda: len(captures()) == 4 and
                     all(lines(p)[-1].startswith('{"type": "call"') for p in captures()),
                     "all four captures to be written")

            files = captures()
            if any(os.path.dirname(p) != out for p in files):
                fail(f"capture written outside --out: {files}")
            for p in files:
                hellos = [l for l in lines(p) if '"hello"' in l]
                if len(hellos) != 1:
                    fail(f"{os.path.basename(p)} holds {len(hellos)} hello records")
            names = [os.path.basename(p) for p in files]
            if not any(n.startswith("trace-7-") and n.count("-") == 3 for n in names):
                fail(f"reconnect did not get a suffixed file: {names}")
            if not any(n.startswith("trace-unknown-") for n in names):
                fail(f"non-integer pid not replaced in file name: {names}")
            if not any("sceKernelRead" in l for p in files for l in lines(p)):
                fail("call after a malformed drops record was lost")

            rx.send_signal(signal.SIGINT)
            log, _ = rx.communicate(timeout=10)
            for s in socks:
                s.close()
        finally:
            if rx.poll() is None:
                rx.kill()
                rx.wait()

        closed = [l for l in log.splitlines() if l.startswith("[-]")]
        if len(closed) != 4:
            fail(f"Ctrl+C summarized {len(closed)} of 4 live targets:\n{log}")
        if "Traceback" in log:
            fail(f"receiver raised:\n{log}")

    print("receiver_smoke: OK")

if __name__ == "__main__":
    main()
