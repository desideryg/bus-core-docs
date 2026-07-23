# bus-core-docs

Documentation for **bus-core-api** — the unified bus ticketing core at `../bus-core-api`.

## How to read this, and the one rule

Documents are numbered, and **a document may only link to a lower-numbered document.**

That single rule is the whole structure. It makes the reference graph a strict DAG: there is no path that
returns to where it started, so nothing you read sends you in a circle, and no fact has two homes that can
drift apart. `tools/check-links.sh` fails if a link ever points upward.

The practical consequence when you are looking something up: **the lowest-numbered document that mentions a
concept is the one that defines it.** Higher-numbered documents use it and assume you have read down.

```
README.md          index — links everywhere, nothing links here

00-glossary.md     vocabulary. Links to nothing.
      ↑
10-module-layout.md      how one module is laid out
11-naming.md             what things are called
      ↑
20-module-catalog.md               the 27 modules and the dependency DAG
21-inter-module-communication.md   how modules reach each other
22-implementation-plan.md          the build order derived from the DAG
      ↑
30-reference-identity-access.md    ← STUDY of a DIFFERENT codebase
31-identity-access-rebuild.md      the plan for building ours
```

## Normative vs informative

| Range | Status | Describes |
|---|---|---|
| **00–29** | **Normative.** These are the rules for this project. | `../bus-core-api` |
| **30–39** | **Informative.** A study of prior art, to learn from. | `../../BUS4/core-bus-api` — **a different codebase** |

Documents in the 30s describe an *earlier, separate* implementation. They are here because it solved these
problems already and its reasoning is worth having. **Nothing in the 30s describes code that exists in this
project.** Each one carries a banner saying so.

If you are an agent working on `bus-core-api`: treat 00–29 as instructions, and 30–39 as background.

## Index

| Doc | What it settles |
|---|---|
| [00-glossary.md](00-glossary.md) | The vocabulary. Read first; everything else assumes it. |
| [10-module-layout.md](10-module-layout.md) | The directory shape of a module, and what may live where. |
| [11-naming.md](11-naming.md) | Module, package, type, column, and permission naming. |
| [20-module-catalog.md](20-module-catalog.md) | What the 27 modules are, the DAG, and how to add one. |
| [21-inter-module-communication.md](21-inter-module-communication.md) | The four ways to cross a module boundary, and when each is right. |
| [22-implementation-plan.md](22-implementation-plan.md) | The build order, derived from the DAG: waves, critical path, phasing. |
| [30-reference-identity-access.md](30-reference-identity-access.md) | *(informative)* How the reference implementation built identity and auth. |
| [31-identity-access-rebuild.md](31-identity-access-rebuild.md) | The slice order for building ours, and the defects not to reproduce. |

## Checking the rule

```bash
bash tools/check-links.sh
```

Verifies every internal link resolves, and that none points at an equal- or higher-numbered document.
