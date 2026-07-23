#!/usr/bin/env python3
"""
Recompute the module implementation waves from the DAG in the code.

    python3 tools/waves.py [path-to-bus-core-api]

The DAG lives in ModuleCatalog.java, which the build already checks against every module's pom. This script
derives the build order from that same source rather than from a hand-maintained list, because a hand-
maintained order silently stops matching the DAG the first time an edge is added — and a stale build order
is worse than none: it is confidently wrong.

A module's WAVE is 1 + the wave of its latest dependency (leaves are wave 0). So every module in a wave can
be built in parallel, and the number of waves is the critical path length.

Emits the markdown table used in 22-implementation-plan.md. If the output differs from what that document
says, the document is out of date — regenerate it, do not edit it by hand.
"""
import re
import sys
from pathlib import Path

# The output is markdown destined for a UTF-8 document. On a Windows console stdout defaults to cp1252,
# which cannot encode the arrows and separators below, so pin it rather than degrade the output.
sys.stdout.reconfigure(encoding="utf-8")

root = Path(sys.argv[1] if len(sys.argv) > 1 else "../bus-core-api")
catalog = root / "architecture-tests/src/test/java/tz/co/otapp/buscore/archtests/ModuleCatalog.java"

if not catalog.is_file():
    sys.exit(f"ModuleCatalog.java not found at {catalog}\nusage: waves.py [path-to-bus-core-api]")

source = catalog.read_text(encoding="utf-8")
dag = {
    m.group(1): set(re.findall(r'"([a-z-]+)"', m.group(2)))
    for m in re.finditer(r'DAG\.put\(\s*"([a-z-]+)"\s*,\s*Set\.of\((.*?)\)\)', source, re.S)
}
if not dag:
    sys.exit("parsed no DAG entries — has ModuleCatalog.java changed shape?")

wave: dict[str, int] = {}


def level(name: str, seen: frozenset = frozenset()) -> int:
    if name in wave:
        return wave[name]
    if name in seen:                      # the build enforces acyclicity; do not hang if it ever slips
        sys.exit(f"cycle reached at {name} — ModuleDependencyTest should have caught this")
    wave[name] = 0 if not dag[name] else 1 + max(level(d, seen | {name}) for d in dag[name])
    return wave[name]


for module in dag:
    level(module)

blocked: dict[str, int] = {m: 0 for m in dag}
for module, deps in dag.items():
    for d in deps:
        blocked[d] += 1

by_wave: dict[int, list[str]] = {}
for module, w in wave.items():
    by_wave.setdefault(w, []).append(module)

print(f"| Wave | Modules | Unblocks |")
print(f"|---:|---|---|")
for w in sorted(by_wave):
    names = sorted(by_wave[w], key=lambda n: (-blocked[n], n))
    cells = " · ".join(f"`{n}`" for n in names)
    counts = ", ".join(f"{n}→{blocked[n]}" for n in names if blocked[n])
    print(f"| **{w}** | {cells} | {counts or '—'} |")

print()
print(f"{len(dag)} modules, {max(wave.values()) + 1} waves.")

# The critical path: walk back from the deepest module, always through a dependency one wave lower.
deepest = max(wave, key=lambda n: wave[n])
path, node = [deepest], deepest
while dag[node]:
    node = next(d for d in sorted(dag[node]) if wave[d] == wave[node] - 1)
    path.append(node)
print("critical path: " + " → ".join(reversed(path)))
