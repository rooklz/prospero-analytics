"""tracefile.py — shared reader for ProsperoTrace JSONL captures.

Not a tool: the tools under host/ import it so they all apply the same
skip-and-continue rule from docs/EVENT_FORMAT.md. A line is skipped when it
is not a JSON object, or when a stable key has the wrong type (`seq` or a
`drops` count that is not a non-negative integer, `mod`/`fn` that are not
strings). Consumers can then index the keys they need without re-checking.
"""
import json

def _is_count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0

def parse(line):
    """Return the event dict for one line, or None if the line is unusable."""
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(ev, dict):
        return None
    if "seq" in ev and not _is_count(ev["seq"]):
        return None
    t = ev.get("type")
    if t == "call":
        if any(k in ev and not isinstance(ev[k], str) for k in ("mod", "fn")):
            return None
    elif t == "drops":
        if not _is_count(ev.get("n", 0)):
            return None
    return ev

def events(path):
    """Yield every usable event in a capture file, in file order."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            ev = parse(line)
            if ev is not None:
                yield ev
