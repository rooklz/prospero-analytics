#!/usr/bin/env python3
"""corpus_smoke.py — catalogue, priority, parity and coveragemap on synthetic data.

Builds a tiny corpus (2 captures, a manifest), then checks the full
Definition-of-done chain: export → import → priority (backlog + missing +
markdown) → parity (missing/extra/matches classification) → coveragemap
(union matrix). Uses only stdlib and the repo's own tools.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tool(name, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "host", name), *args],
                          capture_output=True, text=True)


def fail(msg, out=""):
    print(f"FAIL: {msg}", file=sys.stderr)
    if out:
        print(out, file=sys.stderr)
    sys.exit(1)


def call(seq, fn, mod="libkernel", nid="0x0", ret="0x0"):
    return {"type": "call", "seq": seq, "ts": seq, "tid": 1,
            "mod": mod, "fn": fn, "nid": nid,
            "args": ["0x10", "0x0", "0x0", "0x0", "0x0", "0x0"], "ret": ret}


def write_capture(path, calls):
    with open(path, "w") as f:
        f.write(json.dumps({"type": "hello", "pid": 1, "title": "echo",
                            "fw": "13.40", "seq": 0}) + "\n")
        for ev in calls:
            f.write(json.dumps(ev) + "\n")


def main():
    with tempfile.TemporaryDirectory() as work:
        # ---- corpus: capture A uses Open+Read; capture B uses Open+Net
        a = os.path.join(work, "a.jsonl")
        b = os.path.join(work, "b.jsonl")
        write_capture(a, [call(1, "sceKernelOpen", "libkernel", ret="0x5"),
                          call(2, "sceKernelRead", "libkernel", ret="0x100"),
                          call(3, "sceKernelRead", "libkernel", ret="0x100")])
        write_capture(b, [call(1, "sceKernelOpen", "libkernel", ret="0x5"),
                          call(2, "sceNetSocket", "libSceNet", ret="0x7")])
        nids = os.path.join(work, "nids.txt")
        with open(nids, "w") as f:
            f.write("libkernel sceKernelOpen 0x1\nlibkernel sceKernelRead 0x2\n"
                    "libkernel sceKernelClose 0x3\nlibSceNet sceNetSocket 0x4\n")

        # ---- catalogue
        db = os.path.join(work, "corpus.db")
        r = tool("catalogue.py", "import", db, a, b)
        if r.returncode != 0 or "2 captures, 7 events, 5 calls (2 added this run)" not in r.stdout:
            fail("catalogue import", r.stdout or r.stderr)
        r = tool("catalogue.py", "list", db, "--fw", "13.40")
        if r.returncode != 0 or "2 capture(s)" not in r.stdout:
            fail("catalogue list", r.stdout or r.stderr)
        r = tool("catalogue.py", "list", db, "--title", "nope")
        if "0 capture(s)" not in r.stdout:
            fail("catalogue list filter", r.stdout)
        out = os.path.join(work, "x")
        r = tool("catalogue.py", "export", db, "--out", out)
        if r.returncode != 0 or not os.path.isfile(os.path.join(out, "index.json")):
            fail("catalogue export", r.stdout or r.stderr)
        with open(os.path.join(out, "index.json")) as f:
            idx = json.load(f)
        if len(idx["entries"]) != 2 or not idx["entries"][0]["sha256"]:
            fail("catalogue export index", json.dumps(idx)[:200])

        # ---- priority
        r = tool("priority.py", a, b, "--manifest", nids, "--json", os.path.join(work, "p.json"))
        if r.returncode != 0:
            fail("priority run", r.stdout or r.stderr)
        if "coverage 75.0%" not in r.stdout:
            fail("priority coverage", r.stdout)
        if "sceKernelOpen" not in r.stdout or "sceKernelRead" not in r.stdout:
            fail("priority backlog", r.stdout)
        with open(os.path.join(work, "p.json")) as f:
            rep = json.load(f)
        fns = {(e["mod"], e["fn"]) for e in rep["priority"]}
        if ("libkernel", "sceKernelOpen") not in fns or \
           ("libSceNet", "sceNetSocket") not in fns:
            fail("priority json missing entries", json.dumps(rep["priority"]))
        if {"mod": "libkernel", "fn": "sceKernelClose"} not in rep["missing"]:
            fail("priority json missing list", json.dumps(rep["missing"]))

        r = tool("priority.py", a, "--manifest", nids, "--missing")
        if "libkernel.sceKernelClose" not in r.stdout or "libSceNet.sceNetSocket" not in r.stdout:
            fail("priority --missing", r.stdout)
        r = tool("priority.py", a, b, "--manifest", nids, "--markdown")
        if "`libkernel.sceKernelOpen`" not in r.stdout or "Never touched" not in r.stdout:
            fail("priority --markdown", r.stdout)

        # ---- parity: console has Open/Read, desktop has Open plus an extra,
        # and shares Open at a different rate -> matches/extra/(drifted)
        cons = os.path.join(work, "cons.jsonl")
        desk = os.path.join(work, "desk.jsonl")
        write_capture(cons, [call(1, "sceKernelOpen", "libkernel", ret="0x5"),
                             call(2, "sceKernelRead", "libkernel", ret="0x100"),
                             call(3, "sceKernelRead", "libkernel", ret="0x100"),
                             call(4, "sceKernelRead", "libkernel", ret="0x100")])
        write_capture(desk, [call(1, "sceKernelOpen", "libkernel", ret="0x5"),
                             call(2, "frame_pump", "hostlib", ret="0x1")])
        r = tool("parity.py", cons, desk)
        if r.returncode != 0:
            fail("parity run", r.stdout or r.stderr)
        for needle, label in (("libkernel.sceKernelRead", "missing"),
                              ("hostlib.frame_pump", "extra"),
                              ("libkernel.sceKernelOpen", "drifted")):
            if needle not in r.stdout:
                fail(f"parity classification {label} ({needle})", r.stdout)
        rst = os.path.join(work, "parity.json")
        r = tool("parity.py", cons, desk, "--json", rst)
        with open(rst) as f:
            d = json.load(f)
        missing = [(e["mod"], e["fn"]) for e in d["missing"]]
        extra = [(e["mod"], e["fn"]) for e in d["extra"]]
        if ("libkernel", "sceKernelRead") not in missing or \
           ("hostlib", "frame_pump") not in extra:
            fail("parity json", json.dumps(d)[:300])

        # ---- coveragemap: union of the two priority reports
        r2 = tool("priority.py", b, "--manifest", nids, "--json", os.path.join(work, "p2.json"))
        r = tool("coveragemap.py", os.path.join(work, "p.json"), os.path.join(work, "p2.json"),
                 "--json", os.path.join(work, "cm.json"))
        if r.returncode != 0:
            fail("coveragemap run", r.stdout or r.stderr)
        if "2 report(s)" not in r.stdout or "1/2" not in r.stdout:
            fail("coveragemap matrix", r.stdout)
        with open(os.path.join(work, "cm.json")) as f:
            cm = json.load(f)
        entry = {e["mod"] + "." + e["fn"]: e for e in cm["matrix"]}
        if entry["libkernel.sceKernelRead"]["reports"] != 1 or \
           entry["libSceNet.sceNetSocket"]["reports"] != 2 or \
           entry["libkernel.sceKernelOpen"]["reports"] != 2:
            fail("coveragemap json", json.dumps(cm["matrix"])[:300])

    print("corpus_smoke: OK")


if __name__ == "__main__":
    main()