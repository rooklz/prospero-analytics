#!/usr/bin/env python3
"""session_smoke.py — host/session.py against a fake agent over loopback:
a good capture passes and lands in the database and report, a capture that
breaks EVENT_FORMAT fails validation, and a surface change vs --baseline
fails the session."""
import json
import os
import select
import socket
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def call(seq, fn, mod="libkernel"):
    return {"type": "call", "seq": seq, "ts": seq * 10, "tid": 0, "mod": mod, "fn": fn,
            "nid": "0x0", "args": ["0x1", "0x0", "0x0", "0x0", "0x0", "0x0"], "ret": "0x0"}

GOOD = [{"type": "hello", "pid": 5, "title": "demo", "fw": "13.40", "seq": 0},
        call(1, "socket"), call(2, "connect"), call(3, "close")]

def run(work, events, *extra):
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "host", "session.py"), "--out", work,
                          "--bind", "127.0.0.1", "--port", "0", "--timeout", "20", *extra],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not select.select([p.stdout], [], [], 10)[0]:
        p.kill()
        fail("session printed no banner")
    port = int(p.stdout.readline().split(":")[1].split(",")[0])
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall("".join(json.dumps(e) + "\n" for e in events).encode())
    out, _ = p.communicate(timeout=30)
    return p.returncode, out

def main():
    with tempfile.TemporaryDirectory() as work:
        rc, out = run(os.path.join(work, "a"), GOOD)
        if rc != 0:
            fail(f"good capture failed ({rc}):\n{out}")
        for f in ("traces.db", "report.html"):
            if not os.path.isfile(os.path.join(work, "a", f)):
                fail(f"{f} not written:\n{out}")
        base = [os.path.join(work, "a", "traces", n) for n in os.listdir(os.path.join(work, "a", "traces"))][0]

        bad = GOOD[:2] + [dict(call(3, "close"), args=["0x1"])]
        rc, out = run(os.path.join(work, "b"), bad)
        if rc != 1 or "args not six hex strings" not in out:
            fail(f"format violation not caught ({rc}):\n{out}")

        moved = GOOD[:3] + [call(3, "sceNetSend", "libSceNet")]
        rc, out = run(os.path.join(work, "c"), moved, "--baseline", base)
        if rc != 1 or "+libSceNet.sceNetSend" not in out or "-libkernel.close" not in out:
            fail(f"surface change not caught ({rc}):\n{out}")

        rc, out = run(os.path.join(work, "d"), GOOD, "--baseline", base)
        if rc != 0 or "matches the baseline" not in out:
            fail(f"same surface reported as changed ({rc}):\n{out}")
    print("session_smoke: OK")

if __name__ == "__main__":
    main()
