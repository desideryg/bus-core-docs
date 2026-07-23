# 21 · Inter-module communication

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[20-module-catalog.md](20-module-catalog.md).*

Everything runs in **one process**. "Inter-module" means an in-process call across a compile-time boundary,
not a network hop — unless the event bus is involved.

## The channels

| Channel | Pom edge | Coupling | Reach for it when |
|---|---|---|---|
| **① Published port** | A → B | compile-time, one direction | **Default.** You need an answer or a behaviour now, in this transaction. |
| **② Inbound port** | B → A | compile arrow reversed | The natural edge would close a cycle, or let a core module name an adapter. |
| **③ uid handle** | none | none | You only need to *store* a reference. |
| **④ Outbox event** | none | none at compile time | Something happened, others may care, and you must not block on them. |
| **⑤ Pass-through** | none (A→B, A→C only) | none between B and C | B must **enforce** a value it must not be allowed to **decide**. |
| **⑥ Snapshot at write** | none, after the write | none | The artefact is a *document*, not a screen. |

⑤ and ⑥ are the two ways to end up with **no edge at all**, and they are worth reaching for before ① —
the cheapest dependency is the one you did not take.

```
      ┌───────────────────────── MODULE A ─────────────────────────┐
      │  ① A ─────────── calls ──────────► B.PublishedPort          │
      │  ② A.InboundPort ◄──── implements ──── B.internal.Impl      │
      │  ③ A.table.b_uid ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌► B.table.uid  (no FK)    │
      │  ④ A ──► outbox ──► relay ──► broker ──► B (worker role)    │
      └────────────────────────────────────────────────────────────┘
```

## ① The published port — the default

The callee puts an interface at its **package root**; the implementation lives under `internal/`; the
caller autowires the interface. The pom edge is what permits the import at all.

```java
// modules/identity-access/.../buscore/identityaccess/PrincipalContext.java   ← published root
public interface PrincipalContext {
    Principal require();              // 401 if unauthenticated
    Optional<Principal> current();
}
```

```java
// booking's service, having declared <dependency>identity-access</dependency>
Principal actor = principalContext.require();
```

The caller can never see the implementation — it is under `internal/`, which the boundary rule makes
unimportable. So the seam is the interface, and the implementation can change freely.

**Keep published ports narrow.** No module-wide facade: a caller that only needs to verify one thing must
not compile against session management and credential reset as well.

## ② When the arrow must point the other way

Sometimes the module that *needs* something cannot depend on the module that *has* it, because the reverse
edge already exists. Declare the interface on the **needing** side and implement it on the **owning** side:

```java
// identity-access declares what it needs…
public interface OperatorTenancyLookup {
    Optional<UUID> companyOfOperator(UUID operatorUid);
    Map<UUID, String> operatorNames(Collection<UUID> operatorUids);
}

// …tenancy implements it, under internal/
```

`identity-access` needs an operator's name for its admin surface. But `tenancy` already depends on
`identity-access` for the operator scope, so a direct edge back would close a cycle. This way the only
compile arrow is `tenancy → identity-access`.

Use it for two situations, and only these:

- **The reverse edge already exists** (the case above).
- **A core module must not name an adapter.** Money-critical code declares the port; the vendor adapter
  implements it. `payment-settlement` never names a payment vendor; `payment-gateway-adapter` names
  `payment-settlement`.

**Adapters always point inward, and nothing depends on them.** That is a hand-written negative rule in the
architecture tests, not a habit — a reverse edge would weld a money-critical module to a concrete vendor.

### Fail-closed defaults

When a port may legitimately have no implementation in some deployment, ship a **fail-closed default bean**
rather than letting the context fail to start. A document upload with no object store configured should
raise `503 PROVIDER_UNAVAILABLE`, not silently discard the bytes and not prevent the application booting.
The real implementation is `@Primary` when present.

## ③ Sharing data without calling

A module stores another's identifier as a bare `uuid` column with **no foreign key and no association**:

```java
@Column(name = "operator_uid", nullable = false)
private UUID operatorUid;          // → tenancy's operators.uid. Never joined.
```

A constraint would weld the two schemas together and invert the dependency arrow. The cost is real and must
be accepted deliberately: **nothing detects a dangling handle**, so it must fail closed wherever it is
resolved. A stale uid produces a refusal, never a corrupted join.

### The two universal leaves

Both are depended on by everything, so what goes in each matters:

| Module | Holds | Membership test |
|---|---|---|
| `api-contracts` | error catalog, response envelopes, permission constants, wire enums, paging | *Does it appear on the wire **and** is it needed by more than one module?* |
| `shared` | base entity, audit, translation, money, messaging/outbox, roles | *Is it machinery every module needs?* |

### Start local, promote on second use

**A module's own request and response types live in its `internal/domain/dto`, not here.** Appearing on the
wire is not sufficient — the test is whether a *second* module needs the type.

Promote to `api-contracts` only when a real second consumer appears, and move it in the commit that
introduces that consumer. Until then it stays where it is owned.

The reason is blast radius: `api-contracts` is depended on by 25 modules, so every type placed here turns a
one-module change into a full-reactor rebuild and a shared review surface. A type used by exactly one module
pays that cost and buys nothing.

Both directions of the mistake are real. Centralise everything and you get a flat namespace of hundreds of
types with no module grouping, where changing one response field touches the module everything depends on.
Centralise nothing and two modules quietly grow near-identical view types that drift. The rule above trades
a small, deliberate move at the moment of second use for avoiding both.

**Permission constants are the exception, and they live in `identity-access`.** The obvious placement is
`api-contracts`, on the reasoning that gating a route should not require depending on the identity module.
That reasoning does not survive contact with the DAG: **all 16 modules that gate routes already depend on
`identity-access`**, because they also resolve the acting principal. The dependency exists either way, so
that placement buys nothing.

What it would cost is real. The constants must agree exactly with the SQL seed that inserts them, and the
seed lives in `identity-access`. Split them across two modules and the test holding them to each other has
to reach across a boundary — for an invariant whose failure is silent: a code declared but never seeded
refuses *everyone*, forever, and no other test catches it.

The *guard* is still reached by SpEL bean name, so no module compiles against how the decision is made:

```java
@PreAuthorize("@perm.has('" + Permissions.ROLE_GRANT + "')")
```

**Concatenate the constant; never write the literal.** SpEL is not compiled, so a typo inside the quotes is
not an error — it is a permission nobody holds, which means the route silently refuses everyone forever.

### One database, separate tables

All modules share one PostgreSQL database, but each owns its tables and its own migration history.

> **A module must never read or write another module's tables.** Not with a join, not with a native query,
> not "just for a report".

Be aware this is the one seam **nothing enforces**: the architecture rules read Java bytecode, so a native
query naming another module's table passes every check in the suite. Treat it as a review item, because no
test will catch it.

## ④ Announcing something asynchronously

A module never touches the broker. It calls one method, and the row lands in **its own transaction**:

```java
outbox.enqueue(topic, messageKey, payload);
```

If the business write commits, the event commits with it; if it rolls back, so does the event. Publishing
to a broker directly inside a transaction produces the failure this defeats — broker accepted, database
rolled back, and the rest of the system now believing something that never happened.

A relay then reads committed rows and publishes them. Consumers run in the **worker role only**; `api` and
`gateway` carry no listener.

**Assume at-least-once delivery.** A consumer must be idempotent — the same event may arrive twice, and a
retry must not double-issue a ticket or double-credit a wallet.

**Use it when** the publisher must not care whether anyone is listening. **Do not use it** when you need an
answer, or when the caller's transaction depends on the outcome.

## Decision table

| I need… | Do this | Not this |
|---|---|---|
| one field of theirs, for display | a read-side lookup port returning names; keep it off the write path | a join, or holding their entity |
| to check a permission | the permission constant from `api-contracts`, via the guard bean name | importing `identity-access` to read roles |
| to store a reference to their row | their `uid`, as a bare column | a foreign key, or their entity |
| them to do something, now | call their published port | writing to their tables |
| to say something happened | `enqueue()` to the outbox, in your transaction | calling every interested module in turn |
| a constant both sides use | `api-contracts` if it hits the wire, `shared` if it is machinery | duplicating it, or reaching into their `internal` |
| something from a module that already depends on me | declare an inbound port on my side; let them implement it | adding the reverse edge — that is a cycle |

## What enforces this

| Rule | Catches |
|---|---|
| Maven | An import from a module you never declared. javac refuses; nothing else needs to run. |
| `ModuleDependencyTest` (pom ↔ DAG) | An edge nobody decided on, or an architecture claim the build does not have. |
| `ModuleDependencyTest` (bytecode) | An undeclared edge that Maven's transitive classpath would otherwise permit silently. |
| `ModuleBoundaryTest` | Anything outside a module reaching into its `internal/`. |
| `AnalysisClasspathTest` | A module joining the reactor without joining the analysis — where every rule above reports green while checking nothing. |

**And the gap:** none of them read SQL. Cross-module table access is invisible to all of it.
