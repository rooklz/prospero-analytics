# ProsperoTrace event format

One JSON object per line. The on-console agent
([rooklz/ProsperoTrace](https://github.com/rooklz/ProsperoTrace)) emits
these; the tools in this repo consume them.

## hello

First record on a connection, before any calls.

```json
{"type":"hello","pid":1234,"title":"ftpsrv","fw":"13.40","seq":0}
```

Field notes:
- `fw` is the value the agent was built/run against (informational).

## call

```json
{"type":"call","seq":1,"ts":18273645,"tid":100051,
 "mod":"libkernel","fn":"sceKernelOpen","nid":"0xdeadbeef00000001",
 "args":["0x2000a340","0x0","0x0","0x0","0x0","0x0"],
 "ret":"0x5"}
```

Field notes:
- `seq` is a per-connection monotonic counter; `ts` is microseconds on the
  agent's monotonic clock (may be 0 when the emitter did not supply one).
- `tid` is the target thread id when available, else `0`.
- `args` is always six entries, hex. The agent never dereferences pointers;
  decoding them is the consumer's job.
- `nid` is the 64-bit symbol hash; `mod`/`fn` are the resolved names when the
  agent's table knew the NID, else `mod:"?"`, `fn:"nid_0x…"`.

## drops

Emitted when the agent had to discard events it could not stream:

```json
{"type":"drops","seq":2,"n":137}
```

Consumers should treat `drops` as "the picture is incomplete".

## Compatibility rules

- Keys are stable; new keys may be added.
- `args` stays six entries; unknown extras are ignored by tools.
- Tools must tolerate malformed lines (skip-and-continue), not abort. A line
  is malformed if it is not a JSON object, or if a stable key has the wrong
  type: `seq`/`n` not a non-negative integer, `mod`/`fn` not a string.
  `host/tracefile.py` implements this rule for every tool.