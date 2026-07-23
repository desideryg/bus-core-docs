# 21 · Inter-module communication

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[20-module-catalog.md](20-module-catalog.md).*

Everything runs in **one process**. "Inter-module" means an in-process call across a compile-time boundary,
not a network hop — unless the event bus is involved.

> **Read the Status column before copying anything.** 24 of the 27 modules are empty skeletons today, so
> most of this document is a **contract agreed in advance**, not a description of running code. That is
> deliberate — the shape is argued once, here, rather than settled by whoever writes `booking` first — but a
> reader who mistakes an intention for an implementation goes looking for a class nobody wrote. Where a
> named type does not exist, this document says so.

## The channels

Six ways one module reaches another. **Two are exercised by code today**; the rest are agreed and unbuilt.

| Channel | Pom edge | Coupling | Status | Reach for it when |
|---|---|---|---|---|
| **① Published port** | A → B | compile-time, one direction | **built** — `PrincipalContext` | **Default.** You need an answer or a behaviour now, in this transaction. |
| **② Inbound port** | B → A | compile arrow reversed | none yet | The natural edge would close a cycle, or let a core module name an adapter. |
| **③ uid handle** | none | none | **built** — 3 columns | You only need to *store* a reference. |
| **④ Outbox event** | none | none at compile time | none yet | Something happened, others may care, and you must not block on them. |
| **⑤ Pass-through** | none (A→B, A→C only) | none between B and C | none yet | B must **enforce** a value it must not be allowed to **decide**. |
| **⑥ Snapshot at write** | none, after the write | none | none yet | The artefact is a *document*, not a screen. |

**Four channels take no pom edge, but they are not equivalent.** ③ and ④ remove the *compile* edge and keep
a data or timing coupling; **⑤ and ⑥ remove the relationship entirely** — after a snapshot is written, or a
value is handed over, the two modules have nothing between them at all. Those two are worth reaching for
before ①: the cheapest dependency is the one you did not take.

```
      ┌───────────────────────── MODULE A ─────────────────────────┐
      │  ① A ─────────── calls ──────────► B.PublishedPort          │
      │  ② A.InboundPort ◄──── implements ──── B.internal.Impl      │
      │  ③ A.table.b_uid ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌► B.table.uid  (no FK)    │
      │  ④ A ──► outbox ──► relay ──► broker ──► B (worker role)    │
      │  ⑤ A ──► C.decide() ──► value ──► B.enforce(value)          │
      │  ⑥ A copies B's display values onto its own row, then done  │
      └────────────────────────────────────────────────────────────┘
```

## A request, end to end

> **Nothing below runs yet.** Every module is an empty skeleton, `shared/outbox` and `shared/messaging` are
> reserved packages with no classes, and no module publishes an event today. This is a trace of the channels
> the DAG *permits*, written before the first slice so the shape is argued once rather than settled by
> whoever writes `booking` first. Port and permission names are illustrative; the **edges are not** — every
> one is in `ModuleCatalog.DAG`, and where an edge does not exist this section says so instead of inventing
> it.

One request, the one the whole reactor exists for: **an agent sells a ticket.** `POST /agent/bookings`,
one trip, two seats, paid from the agent's wallet.

Hops 1–16 become buildable at **wave 11** (`booking` is wave 10, `payment-settlement` wave 11); hops 17–19
at waves 12–13. Until then this is a contract, not a description.

```
  agent's handset
        │  POST /agent/bookings        Idempotency-Key: 8f3c…      audience: /agent/**
        ▼
 ┌──────────────────────────── booking · ONE TRANSACTION, ONE COMMIT ────────────────────┐
 │
 │  1  ──①──►  identity-access    who is this, and may they create a booking
 │  2  ──①──►  identity-access    whose rows may they touch  (scope — always a 2nd check)
 │  3  ──①──►  agent              may THIS agent sell THIS route for THIS operator today
 │  4  ──①──►  scheduling         trip exists, is sellable, and has N materialised seats
 │  5  ──①──►  network            (board, alight) is a legal ordered pair on that route
 │  6  ──①──►  fare               quote the leg   ──⑥──►  frozen onto the booking row
 │  7  ──①──►  quota              consume the agent's allocation
 │            ⑤   trip capacity from hop 4 is passed in — quota may not fetch it
 │  8  ──①──►  promotions         evaluate        ──⑥──►  frozen discount line
 │  9  ──①──►  customer           find-or-create golden record  ──③──►  customer_uid
 │ 10  ──①──►  seat-inventory     HOLD the seats           ← the double-sell arbiter
 │
 │ 11  ──②──►  booking.SalePayment                     ┐  declared BY booking,
 │                    │                                │  implemented IN
 │                    ├─12 ──①──► wallet-ledger        │  payment-settlement/internal —
 │                    │           debit + commission   │  so the only compile arrow
 │                    ├─13   settlement row written    │  stays
 │                    │      ──④──► outbox row         │  payment-settlement ──► booking
 │                    ▼                                ┘
 │ 14  ──①──►  seat-inventory     hold ──► allocation
 │ 15           booking row + ⑥ fare + ⑥ discount + ③ uid handles
 │ 16  ──④──►  outbox row: booking.confirmed           ← same transaction as 15
 └──────────────────────────────────── COMMIT ───────────────────────────────────────────┘
        │
        │   everything above commits together, or none of it happened
        ▼
     relay  reads committed outbox rows  ──►  broker  ──►  worker role only
        │
        ├─17 ──④──► notification   then ──①──► booking, scheduling, network, tenancy,
        │                          agent to render the SMS. Must be idempotent.
        ├─18 ──④──► worker ──②──► payment-settlement's fiscal port ◄── fiscal-adapter
        └─19 ──④──► worker ──②──► booking's regulator port         ◄── uts-adapter
```

### The walkthrough

| # | Caller → callee | Channel | Why this channel, and the failure it prevents |
|---:|---|---|---|
| 1 | `booking` → `identity-access` | **① published** | Booking needs the principal *now* and must refuse without it. The permission constant comes from `identity-access.Permissions`; the guard is reached by SpEL bean name, so booking never compiles against how the decision is made. Not ③: an `agentUid` in the request body is a claim, not a fact — **authority is read from the principal, never from a body**, which is what stops one agent selling under another's identity. |
| 2 | `booking` → `identity-access` | **① published** | Scope answers *whose*, permission answers *what*, and **both checks always run**. A separate call because they are distinct causes with distinct codes — an agent who lacks `BOOKING.CREATE` and one reaching another operator's trip have different fixes, and a client that cannot tell them apart can act on neither. |
| 3 | `booking` → `agent` | **① published** | `agent` fails closed by design, so booking must get a live yes/no. Not ⑥ snapshot: a selling grant is a decision at the moment of sale — snapshot it and a revoked agent keeps selling until something refreshes. Not ③: a stored uid proves the agent exists, not that they may sell this route today under this limit. `agent → network` exists, so `agent` resolves the route itself; booking does not pass it a route it looked up on the agent's behalf. |
| 4 | `booking` → `scheduling` | **① published** | The trip must exist and be sellable *this instant* — departed or cancelled has to refuse. Note **`booking` has no `fleet` edge**: the seat count reaches booking as scheduling's *materialised* seats, never as fleet's layout. That prevents booking selling against a layout that no longer matches what was materialised when the vehicle was swapped. |
| 5 | `booking` → `network` | **① published** | `network` owns ordered route stops. Booking asks whether `(board, alight)` is a legal forward pair rather than deriving it — a second copy of stop ordering is a second thing to get wrong, and it fails by selling a leg that runs backwards. |
| 6 | `booking` → `fare` | **① published**, then **⑥ snapshot** | ① because booking needs the number now and must never guess a price. ⑥ because the ticket is a *document, not a screen*: the fare table edited next quarter must not silently reprice a ticket sold today, and a reprint must show what was sold. `fare → network, scheduling, fleet` all exist, so fare resolves the leg and the seat class itself. |
| 7 | `booking` → `quota` | **① published** + **⑤ pass-through** | ① because the allocation decrement must be *in booking's transaction* — an abandoned sale then releases it on rollback, with no sweeper to write and no sweeper to forget. ⑤ because **`quota` depends on nothing but the two leaves**: it cannot call `scheduling` for the trip's capacity or `agent` for the agent. So booking, which depends on both, passes the capacity in. Quota **enforces** the yield rule; `scheduling` **decides** the capacity. The alternative — quota keeping its own copy of trip capacity — drifts the first time a 49-seat coach is swapped for a 33. Quota holds agent, sub-route and trip uids as **③ bare handles** and resolves them against nothing, which is exactly what keeps `booking → quota` acyclic. |
| 8 | `booking` → `promotions` | **① published**, then **⑥ snapshot** | Same shape as fare, and the catalog already names it: *"a frozen discount line the sale snapshots."* `promotions` depends on **no sale-path module** — that absence is what keeps `booking → promotions` acyclic — so it cannot call back to ask what the booking looks like. Booking passes everything the rule needs. |
| 9 | `booking` → `customer` | **① published**, then **③ uid handle** | ① to find-or-create the golden record and get the uid now. ③ to store it: no FK, no association. `customer` is platform-global on purpose — **no row carries an operator_uid** — and golden records get merged and re-keyed. A constraint from booking would freeze that and invert the arrow. Fails closed on a dangling handle: a refusal, never a corrupted join. |
| 10 | `booking` → `seat-inventory` | **① published** | The one hop that *must* be a synchronous contended write. Two agents on the same seat in the same second is the precise failure this module exists to prevent, and **an event cannot refuse** — ④ here confirms both. `seat-inventory → agent` exists, so the hold is attributed to the selling agent without booking passing it separately. |
| 11 | `booking` → `payment-settlement` | **② inbound port** | Booking declares `SalePayment` at its own root; `payment-settlement` implements it under `internal/`. **The reverse edge already exists** (`payment-settlement → booking`), so this is ②'s first case verbatim. Not ④: the outbox is explicitly ruled out when the caller's transaction depends on the outcome, and here it does — a `booking.reserved` event issues the ticket first and discovers the empty wallet second, which is an agent selling past a zero balance and a reconciliation job chasing it. **See the note below: this hop is the one the catalog does not settle.** |
| 12 | `payment-settlement` → `wallet-ledger` | **① published** | Needs an answer — sufficient balance — inside the same transaction. Balance is **derived, never stored**, so the check is a computed sum and the debit is an append of an immutable entry under the same lock. The entry carries the idempotency key, which is what makes a retry safe rather than a double-debit. `payment-settlement → agent, promotions` exist, so the commissionable base is computed from the agent's rule and the frozen discount without a further hop through booking. |
| 13 | `payment-settlement` → its own outbox | **④ outbox** | The settlement row and its event land together. Publishing to a broker directly here produces the failure the outbox defeats: **broker accepted, database rolled back**, and the fiscal adapter now receipting a payment that never happened. |
| 14 | `booking` → `seat-inventory` | **① published** | Hold becomes allocation, still inside the transaction, so the seat and the money change state at the same instant. Split them and there is a window where the wallet is debited and the seat is not yours. |
| 15 | `booking` writes its own tables | — | Booking row, ⑥ fare line, ⑥ discount line, ③ handles for trip, agent, operator and customer. **No module writes another's tables** — this is the one seam nothing enforces, because the architecture rules read bytecode and a native query naming `wallet_entries` passes every check in the suite. |
| 16 | `booking` → its own outbox | **④ outbox** | `outbox.enqueue("booking.confirmed", bookingUid, payload)` — one method, a row in booking's own transaction. ④ because the publisher **must not care whether anyone is listening**: a ticket is sold whether or not notification, reporting and the regulator adapter are up. |
| 17 | relay → broker → `notification` | **④ outbox** | ④ **because the DAG leaves no alternative.** `notification` depends on `booking`, `payment-settlement`, `wallet-ledger`, `scheduling`, `network`, `tenancy` and `agent` — every module on the sale path. A call *into* notification from any of them closes a cycle with all seven. So the sale announces and does not call. Notification then uses its own ① edges to render the SMS, which is why the event carries a booking uid and not a whole ticket. **At-least-once**, so dispatch dedupes on (event id, channel, recipient) — the retry that texts a passenger twice is the cheap version of the retry that double-credits a wallet. Consumers run in the **worker role only**; `api` and `gateway` carry no listener. |
| 18 | worker → `payment-settlement`'s fiscal port ← `fiscal-adapter` | **④ outbox**, then **② inbound port** | ② is the *second* case: **a money-critical module must not name a vendor.** `payment-settlement` declares the port; `fiscal-adapter` implements it and names the revenue authority. **Adapters point inward and nothing depends on them** — a review rule, not an enforced one (see ②), because a reverse edge would weld settlement to one tax regime. ④ drives it because the call leaves the process. |
| 19 | worker → `booking`'s regulator port ← `uts-adapter` | **④ outbox**, then **② inbound port** | Identical shape: `uts-adapter → booking` exists, booking declares the port. If the regulator is unreachable the deployment ships a **fail-closed default bean** raising `503` (`CommonErrors.SERVICE_UNAVAILABLE`) rather than failing the context to start — and rather than silently dropping a submission. |

### Edges this trace deliberately does not take

Naming these matters more than naming the ones it does. Each is a real absence in `ModuleCatalog.DAG`.

| Wanted | Status | What to do instead |
|---|---|---|
| `booking → payment-settlement` | **Impossible** — `payment-settlement → booking` exists; this is a cycle | ② inbound port, hop 11 |
| anything on the sale path `→ notification` | **Impossible** — notification depends on all seven | ④ outbox, hop 17 |
| `booking → wallet-ledger` | **Absent, and legal to add** — no cycle results | Don't. It gives the sale path two modules writing money, and settlement state split across two owners. Route it through `payment-settlement`, which owns settlement state and the gateway port. |
| `booking → fleet` | **Absent** | Seats reach booking via `scheduling`'s materialised seats or `seat-inventory` |
| `payment-settlement → accounting-ledger` | **Absent — and nothing depends on `accounting-ledger` at all** | ④ only. But note `accounting-ledger` depends on the two leaves alone, so it cannot name `payment-settlement`'s payload type: either the event payload is promoted to `api-contracts` (it hits the wire and a second module needs it — it passes the test) or it is untyped. That is an unresolved decision, not a solved one. |
| anything → `reporting` | **Absent — nothing depends on `reporting`** | ④ only, same payload problem. It is a leaf and never a source of truth. |
| anything → `exchange-rate` | **Absent — nothing depends on `exchange-rate` today** | A multi-currency sale has **no path through the current DAG**. That edge has to be argued for in a PR, not assumed to exist. |

**The one hop the catalog does not settle is 11.** The DAG fixes the *direction* — `payment-settlement → booking`, so booking can never call it — but it is silent on the *channel*, and both ② and ④ are structurally available. This section picks ② because the doc's own rule for ④ excludes it: *do not use it when the caller's transaction depends on the outcome.* If the first implementer chooses ④ instead, the ticket becomes RESERVED-then-CONFIRMED and everything in the next subsection changes. Argue it in the PR that writes it; do not let it arrive by default.

### Where the transaction boundary is

One process, one datasource, one commit. Hops 1–16 are in-process calls through interfaces, not network hops, so **they share the caller's transaction** — including hop 12, the wallet debit, which is why a sale is atomic without a distributed transaction anywhere in it.

```
   1 ─ 2 │ 3 ─────────────────────────────── 16 │ COMMIT │ 17 ─ 18 ─ 19
  filter │        booking's transaction         │        │  after, always
  chain  │  reads, quota, seat hold, wallet     │        │  never able to un-sell
```

| Stage | In the transaction? | What happens on failure |
|---|---|---|
| 1–2 authenticate, scope | **No** — the filter chain resolves the principal before the service method opens one | 401 or a scope refusal. No transaction ever started; nothing to roll back. |
| 3–5 grant, trip, leg | Yes, read-only | Refusal. Nothing written yet, so rollback is free. |
| 6 fare | Yes, read-only | If fare cannot price the leg, **refuse**. Never sell at a guessed price — an unpriceable leg is a configuration gap, and a default fare hides it until reconciliation. |
| 7 quota | Yes — **a write** | `QUOTA.EXHAUSTED`. This is the point of putting the decrement inside: a sale that dies at hop 10 or 12 releases the allocation on rollback. No sweeper, so no sweeper to forget to write. |
| 8 promotions | Yes, read-only | *Unsettled.* "No promotion applies" is a normal answer and the sale proceeds at full fare. Whether promotions being **unavailable** should refuse the sale or fall through to full fare is a decision with two named failures — refusing loses revenue on a healthy trip, falling through sells at the wrong price and pays the wrong commission. Decide it in the PR. |
| 9 customer | Yes — a write | Rollback. No orphan golden record. |
| 10 seat hold | Yes — **a contended write** | `BOOKING.SEAT_TAKEN`, and rollback releases the quota taken at 7. Holding the seat row for the transaction's duration is what makes double-sell impossible — and it is exactly why **no vendor HTTP call may be inside this boundary**: the transaction has to stay short because a contended row is inside it. |
| 11–13 payment | Yes | Insufficient funds rolls back **the seat hold and the quota with it**, in the same instant, and the seat is back on sale before the agent's screen refreshes. This is the strongest argument for ② over ④: with ④ the seat is held for the TTL against a sale that could never have completed, and the passenger standing at the next counter is told the bus is full. |
| 14 allocate | Yes | Rollback takes the wallet debit with it. **The agent is not charged for a seat they did not get** — not "is refunded", not charged. |
| 15 booking row | Yes | Rollback. |
| 16 outbox row | **Yes — this is the property** | It cannot fail on its own. `outbox.enqueue()` writes a row in booking's transaction; if the business write commits the event commits with it, and if the write rolls back the event rolls back with it. There is no window in which the broker has been told about a sale the database does not have. Publish to the broker directly here instead and you get exactly that: **broker accepted, database rolled back, and the rest of the system now believing something that never happened** — an SMS to the passenger, a fiscal receipt, and a regulator submission for a ticket nobody holds. |
| — | **COMMIT** | Everything above, or none of it. |
| 17–19 relay, notification, adapters | **No** — after commit, worker role | Relay down: events are *delayed, not lost* — the rows are committed and sit there until it comes back. Process dies between commit and publish: same, the relay resumes, which is why delivery is at-least-once and consumers dedupe. Notification down: the SMS is late; **the ticket is still valid, because the ticket is a ⑥ snapshot and not a message**. Regulator or revenue authority timing out: retried, and the sale stands. |

Two rules fall out of that line, and both are worth stating as rules rather than leaving as consequences:

**Nothing downstream of the commit may un-sell the ticket.** A fiscal receipt that fails is a receipt to retry, not a booking to reverse. Reversal is a new, compensating transaction with its own booking state and its own ledger entries — never a rollback of a committed sale.

**Nothing downstream of the commit may be required for the ticket to be valid.** The moment boarding depends on the SMS having arrived, the broker is in the critical path of a bus leaving a station.

**A card sale does not have this shape, and the difference is instructive.** Hop 12 can be synchronous *only because wallet-ledger is in this process*. A card payment leaves through `payment-gateway-adapter` — an external call, therefore never inside the boundary. The booking commits `RESERVED`, the seat is held with a TTL rather than allocated, and confirmation arrives later on a **signed callback**, which is a second transaction that must be idempotent because the vendor will retry it. Same DAG, same channels, one hop moved outside the commit, and every failure mode in the table above changes with it.

## ① The published port — the default

The callee puts an interface at its **package root**; the implementation lives under `internal/`; the
caller autowires the interface. The pom edge is what permits the import at all.

**The interface/implementation split is the rule for a port that crosses a module edge — not for everything
at a package root.** `PermissionGuard` and `OperatorScopeResolver` are published as concrete `@Component`
classes with no interface, because neither is a seam anybody needs to substitute: one is reached by SpEL
bean name and never named as a type, the other is fifteen lines of branching over a `Principal`. An
interface there would be a second file that adds a name and hides nothing.

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

*(The `booking` half is illustrative — the module is an empty skeleton. The pom edge
`booking → identity-access` is real; the call site is not written yet. `PrincipalContext` and its
`internal/` implementation `CurrentPrincipal` are real, and are this channel's only built instance.)*

The caller can never see the implementation — it is under `internal/`, which the boundary rule makes
unimportable. So the seam is the interface, and the implementation can change freely.

**Keep published ports narrow.** No module-wide facade: a caller that only needs to verify one thing must
not compile against session management and credential reset as well.

## ② When the arrow must point the other way

Sometimes the module that *needs* something cannot depend on the module that *has* it, because the reverse
edge already exists. Declare the interface on the **needing** side and implement it on the **owning** side:

> **No inbound port exists yet.** `OperatorTenancyLookup` below is named in this document and in
> [11-naming.md](11-naming.md) and **nowhere in the code** — `tenancy` is an empty skeleton and could not
> implement it. Channel ② has zero instances. It is documented now because the first one will be written
> under deadline, and the shape is easier to agree in advance than to argue about then.

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

**Adapters always point inward, and nothing depends on them.**

**This is a review rule, not an enforced one, and the doc used to claim otherwise.** There is no
hand-written negative rule anywhere in the architecture tests. The property holds only because no module's
entry in `ModuleCatalog.DAG` lists an adapter, and the generic bytecode rule then forbids the undeclared
edge. **A single commit that adds `payment-gateway-adapter` to `booking`'s pom *and* to `ModuleCatalog.DAG`
leaves the entire suite green** — which is precisely the case the rule exists to stop, since a reverse edge
would weld a money-critical module to a concrete vendor.

If that matters enough to be a rule, it should be an ArchUnit rule asserting that no module named `*-adapter`
appears in any other module's dependency set. Until somebody writes it, this is a thing reviewers must
notice, and saying so is more useful than a sentence insisting it is automatic.

### Fail-closed defaults

When a port may legitimately have no implementation in some deployment, ship a **fail-closed default bean**
rather than letting the context fail to start. A document upload with no object store configured should
raise `503` (`CommonErrors.SERVICE_UNAVAILABLE`), not silently discard the bytes and not prevent the
application booting. The real implementation is `@Primary` when present.

*(A convention, not yet exercised: no fail-closed default bean and no `@Primary` bean exists anywhere in the
reactor. `storage` and `documents` are skeletons.)*

## ③ Sharing data without calling

A module stores another's identifier as a bare `uuid` column with **no foreign key and no association**:

```java
// identity-access/.../entity/StaffOperator.java — a real one, not an illustration
@Column(name = "operator_uid", nullable = false)
private UUID operatorUid;          // → tenancy's operators.uid. No FK, no association, never joined.
```

Every bare handle in the system today points from `identity-access` at `tenancy`, which does not exist
yet — the handles were written first because the alternative was to design the boundary later, once code
had grown across it:

| Column | On | Points at | Why not a foreign key |
|---|---|---|---|
| `staff_identities.company_uid` | a staff login | a company | `tenancy` is wave 4; a constraint would invert the arrow from wave 2 |
| `staff_operators.operator_uid` | a membership | an operator | same, and it is resolved on every sign-in |
| `staff_operators.company_uid` | a membership | a company | duplicated deliberately, so a **composite FK within `identity-access`** can hold the pair together |

That last row is the interesting one. A bare handle gives up referential integrity *across* modules — but
integrity *within* one is still available, and `staff_operators` uses it: the pair
`(staff_identity_id, company_uid)` is a composite foreign key onto `staff_identities`, which makes a
cross-company membership impossible to write. **Losing the arrow to another module does not mean losing
constraints altogether**, and reaching for the ones still available is the difference between a rule that
is enforced and a rule that is remembered.

A constraint would weld the two schemas together and invert the dependency arrow. The cost is real and must
be accepted deliberately: **nothing detects a dangling handle**, so it must fail closed wherever it is
resolved. A stale uid produces a refusal, never a corrupted join.

### The two everything depends on

**Only `api-contracts` is a true leaf.** `shared` depends on it, so the two are a chain rather than a pair —
`api-contracts` is depended on by 26 modules, `shared` by 25. (`ModuleCatalog`'s own javadoc calls them both
leaves; it is wrong in the same way this document was.) What goes in each still matters more than the
distinction. **The middle column is what is there
today**, not what is planned — a doc that lists intentions in the present tense is how somebody comes
looking for a type that was never written.

| Module | Holds today | Reserved for | Membership test |
|---|---|---|---|
| `api-contracts` | `ApiResponse`, `ErrorDetail`, `PageMeta`, `ErrorCode`, `CommonErrors`, `ApiException`, `DescribedEnum` | wire enums shared by two modules | *Does it appear on the wire **and** is it needed by more than one module?* |
| `shared` | `BaseEntity`, `Uuids`, `Times`, `LogSanitizer`, `PageRequests` | audit, translation, money, messaging/outbox | *Is it machinery every module needs?* |

**Permission constants are in neither.** They live in `identity-access` — see below, it is the one
deliberate exception and the reasoning is worth reading before moving them.

### Start local, promote on second use

**A module's own request and response types live in its `internal/domain/dto`, not here.** Appearing on the
wire is not sufficient — the test is whether a *second* module needs the type.

Promote to `api-contracts` only when a real second consumer appears, and move it in the commit that
introduces that consumer. Until then it stays where it is owned.

The reason is blast radius: `api-contracts` is depended on by **26** modules, so every type placed here
turns a one-module change into a full-reactor rebuild and a shared review surface. A type used by exactly one module
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

> **Not built yet.** `shared/outbox` and `shared/messaging` are reserved packages with no classes in them,
> and no module publishes an event today. This section is the contract the first publisher must be held to,
> not a description of running code — it is here because the shape has to be agreed before the first one is
> written, not after.

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

## ⑤ Enforcing a rule you are not allowed to decide

> **No instance yet.** `quota`, `seat-inventory` and `booking` are skeletons. What *is* already decided, and
> is in the poms and in `ModuleCatalog.DAG` today, is the edge set: **`seat-inventory` does not depend on
> `quota`, and `booking` depends on both.** `quota` has exactly one consumer in the entire DAG, and it is the
> orchestrator. The channel is committed; only the classes are missing.

`seat-inventory` is the double-sell arbiter. Part of what it must refuse is an agent taking more seats on a
trip than that agent is allowed — but **the allowance is not `seat-inventory`'s to decide.** It is a yield
rule, and yield rules belong to `quota`.

The obvious move is an edge, `seat-inventory → quota`. It would even be acyclic — nothing stops it. **This is
not a cycle-avoidance channel; ② is for cycles. ⑤ is for the edge that would compile fine and still be the
wrong shape.**

Instead the orchestrator reads the number and hands it over:

```
  agent sells ──►  booking  ──── ① ────►  quota           DECIDES the rule; owns the table
                      │
                      └──── ① ────►  seat-inventory       ENFORCES 5; refuses the 6th seat;
                             (ceiling = 5)                 never asks where 5 came from

  seat-inventory ╌╌╌╌╌╌╌╌╌ ✗ ╌╌╌╌╌╌╌╌╌► quota             the edge not taken: not in the pom,
                                                           not in the DAG, not in the rebuild set
```

`booking` already holds both edges. The pass-through costs **zero new edges** and leaves **zero coupling
between the two modules that would otherwise have met.**

**Why it beats the edge.** *The rule keeps one home* — take the edge and `seat-inventory` becomes a second
place the allowance is decided, not on the day it is added but on the day somebody writes
`if (noQuotaRow) applyDefault()` inside the enforcer. A rule with two homes is a rule nobody owns, and the
divergence is silent: both modules run, both look right alone, and the number on the quota screen is not the
number that refused the sale. *One enforcer serves callers whose rules differ* — `charter` depends on
`seat-inventory` and not on `quota`, because whole-bus hire has no per-agent allocation at all; had the
enforcer taken the edge, `charter` would inherit `quota` and rebuild on every quota change for a rule it
never applies. *The enforcer stays testable alone* — "the sixth seat is refused" means passing `5` and
asserting a refusal, with no quota fixture and no quota schema.

### The danger, and what bounds it

A caller can hand over the wrong number, and nothing in the type system stops it. Three things bound it:

- **The caller set is closed and enumerable.** Only a module with a `seat-inventory` edge can make the call,
  and the DAG lists them. A rule enforced against a finite set of in-process callers, all compiled in this
  reactor, is a *review* problem. A rule enforced against the open internet is a *security* problem. Do not
  confuse the two in either direction.
- **The enforcer keeps its own invariants regardless.** A wrong ceiling can let an agent oversell an
  allocation. It cannot sell one seat twice — that is `seat-inventory`'s own invariant, enforced by its own
  constraint, and no argument reaches it. **The blast radius is bounded by what B still owns independently**,
  and if that boundary is not obvious, the value should not be passed in.
- **The value is read fresh, in the same transaction as the enforcement.** A ceiling read in an earlier
  request and carried forward is a stale rule, and the staleness is invisible.

### Fail closed on absent — never open

The passed-in value must be **required and total**. The shape that kills this channel is an optional one:

```java
void reserve(ReserveSeats command, Integer maxSeats);   // null means…?
```

Whatever it means today, somebody will make it mean *no limit*, and then an agent with no quota row sells the
whole bus. This is the same defect as `if (operatorUids.isEmpty()) skip the WHERE clause` in ③ — **an absent
rule read as unrestricted rather than as a refusal.** "Unbounded" is a decision, so `quota` makes it and says
so, through one named constructor a reviewer can grep for.

### When it is not a pass-through at all

> **If a value could reach the enforcer from a request, it is not a pass-through — it is an authority field
> with extra frames on the stack.**

Passing a value through three in-process frames launders nothing. A number that entered through a request
body is a request body number when it arrives.

| Situation | Why not | Instead |
|---|---|---|
| The value originates in the request, even indirectly | The client is setting its own limit | B derives it, or the request never carries it |
| B is enforcing a rule *against* the caller's principal | The constrained party supplies the constraint | ① at the point of decision, or ② |
| It is money — amount, discount, commission, wallet ceiling | `fare`, `promotions` and `wallet-ledger` decide these, and a balance is *derived, never stored* | ① at the decision, or ⑥ for a frozen line |
| Whether this agent may sell this trip at all | Selling authority is `agent`'s, resolved from the principal | Resolve it; never accept it as a parameter |

**The realistic failure is not a malicious caller.** It is a two-step flow: step one returns `maxSeats: 5` to
the browser so the UI can grey out the sixth seat, and step two accepts it back "so the server need not look
it up again". The ceiling is now client-supplied and the channel has become the vulnerability. **Return it if
the UI needs it; never read it back.**

### The signature that makes the value obvious rather than smuggled

```java
// modules/seat-inventory/.../seatinventory/SeatAllocationCeiling.java   ← the ENFORCER's root, not quota's
/** A ceiling seat-inventory enforces and does not decide. It never learns who decided what. */
public record SeatAllocationCeiling(int maxSeats, String decidedBy) {
    public SeatAllocationCeiling {
        if (maxSeats < 0) throw new IllegalArgumentException("ceiling must not be negative");
        Objects.requireNonNull(decidedBy, "a ceiling must name the rule that produced it");
    }
    /** The only way to lift it — one call-site shape, greppable in review. */
    public static SeatAllocationCeiling unbounded(String decidedBy) { … }
}

public interface SeatReservations {
    Reservation reserve(ReserveSeats command, SeatAllocationCeiling ceiling);   // required, second argument
}
```

**The ceiling type belongs to `seat-inventory`, not to `quota`.** If the enforcer's signature named quota's
type, the import would be the edge we just avoided. The enforcer publishes the shape of what it must be
handed; the orchestrator translates — and that translation line is where the pass-through becomes visible:

```java
// booking — the only module holding both edges, so the only place the two rules meet
AgentSeatAllocation allowed = seatAllocationRules.forAgentOnTrip(agentUid, tripUid);   // quota decides
Reservation held = seatReservations.reserve(command,
        new SeatAllocationCeiling(allowed.maxSeats(), allowed.ruleCode()));            // seat-inventory enforces
```

Three shapes that lose the property, worst last:

```java
Reservation reserve(ReserveSeats command, Integer maxSeats);              // smuggled: an int reads as a hint
record ReserveSeats(UUID tripUid, …, int maxSeats) { }                    // hidden: one field among twenty
class SeatReservationsImpl { private final SeatAllocationRules quota; }   // the edge: the rule has two homes
```

**The cost.** Pass-through moves work onto the orchestrator, and it does not scale past a handful of values.
If B needs five decided numbers from five modules, the honest question is no longer "which channel" — it is
whether B is enforcing something that belongs in A, or whether those five rules are one rule wearing five
names.

## ⑥ Freezing what was sold

> **No instance yet.** `booking`, `fare` and `promotions` are skeletons. But the catalog already commits to
> it in words: `fare` owns *"the quote a sale snapshots"*, `promotions` owns *"a frozen discount line the
> sale snapshots"*.

A ticket says the fare was 18,500 and the route was *Dar es Salaam → Morogoro (via Chalinze)*. A year later
the fare is 21,000 and the route has been renamed. **The ticket must still say what was sold.**

So the values are **copied onto the booking row at the moment of sale** rather than joined at read time.

### Telling a document from a screen

| | Screen | Document |
|---|---|---|
| Answers | "what is true now?" | "what was agreed then?" |
| Correct behaviour when the source changes | update | **do not** update |
| Example | the trip list an agent browses | the ticket, the receipt, the settlement line |
| Channel | ① live call, or ③ handle + lookup | **⑥ snapshot** |

The test is one question: **if the source value changed tomorrow, would this artefact be wrong, or would it
be a forgery?** A trip list showing yesterday's price is wrong. A ticket showing today's price for a sale
made yesterday is a forgery.

### Correctness, not speed

This is denormalisation, and it is not the denormalisation people argue about. The speed argument says *copy
it to avoid a join* — and invites you to do it everywhere, then keep the copies in sync with triggers and
sweepers.

**The correctness argument says the opposite: these copies must never be synced.** A background job that
"repaired" stale fares on old tickets would be destroying evidence. Getting the two confused produces the
worst outcome available — a snapshot that is *sometimes* refreshed, so nobody can tell which tickets are
historical fact and which are today's fare wearing an old date.

### What is copied, and what stays a handle

**The uid stays; the display values are copied.** You still need to navigate — "show me every ticket on this
trip" is a real query — so the handle remains, and it remains a bare ③ handle with no foreign key.

```sql
CREATE TABLE bookings (
    ...
    -- ③ handles: still resolvable, still no FK. Navigation.
    trip_uid            uuid           NOT NULL,
    operator_uid        uuid           NOT NULL,
    customer_uid        uuid           NOT NULL,

    -- ⑥ snapshot: what was sold. NEVER updated after insert, by anything, ever.
    fare_amount         numeric(12,2)  NOT NULL,
    fare_currency       varchar(3)      NOT NULL,
    fare_rule_code      varchar(64)     NOT NULL,   -- WHICH rule priced it, not just the number
    route_description   varchar(256)    NOT NULL,
    operator_name       varchar(128)    NOT NULL,
    departure_at        timestamp       NOT NULL,
    seat_label          varchar(8)      NOT NULL,
    passenger_name      varchar(128)    NOT NULL
);
```

Note `fare_rule_code`. **Snapshot the reason as well as the number**, or a year later nobody can answer why
this ticket cost that — and "why" is the question an audit actually asks.

```
   joined at read                          snapshotted at write
   ─────────────                           ────────────────────
   ticket ──► trip ──► route.name          ticket.route_description  ← copied once
          └─► fare_table.amount            ticket.fare_amount        ← copied once

   route renamed  ⇒  every historical      route renamed  ⇒  new sales say the new name,
   ticket silently changes                 old tickets still say what was sold
```

### The cost: a snapshot cannot be repaired at the source

Fixing a typo in a route name fixes nothing on tickets already sold — correctly. A genuine correction is
therefore an **explicit re-issue**: void the old artefact, issue a new one, keep both. That is more work than
an `UPDATE`, and it is the same work the accounting rule demands anyway — you do not edit an issued document,
you supersede it.

### What it removes

Once the values are on the row, `booking` needs `fare` for **nothing** to render a ticket. Reprinting one
touches a single table and cannot be broken by anything happening in `fare`, `network` or `tenancy`. The
compile edge from the sale path stays because the *sale* needs it; the read path stops depending on any of
them. **A snapshot is the only channel that gets cheaper over the artefact's life**: after the write there is
no relationship left to maintain.

## Anti-patterns, with the code that looks reasonable

None of these look like mistakes at the moment they are written. That is what makes them worth listing.

### 1 · The cross-module join — the one nothing catches

```java
// in booking, "just for the agent's sales report"
@Query(value = "SELECT b.*, w.balance FROM bookings b "
             + "JOIN wallet_entries w ON w.agent_uid = b.agent_uid", nativeQuery = true)
```

**Why it looks reasonable.** One query instead of two. No new pom edge — so `ModuleDependencyTest` stays
green, `ModuleBoundaryTest` stays green, and the whole suite reports success.

**What it costs.** `wallet-ledger` can no longer change its own table without breaking a module that never
declared it. Worse, this reads a balance that is **derived, never stored** — so the number is wrong the
moment there is an entry the naive sum does not account for.

**The failure is that nothing tells you.** The architecture rules read *bytecode*. A string containing
another module's table name is invisible to every one of them. **This is the single most important review
item in this document**, because it is the only rule with no automated backstop at all.

**Instead:** ① for a live number, ④ + the reporting module for a report.

### 2 · The module-wide facade

```java
public interface IdentityAccessService {          // published root
    Principal currentPrincipal();
    void grantRole(UUID staffUid, String roleCode);
    PasswordResetIssued issueReset(UUID staffUid);
    LoginResponse login(LoginRequest request);
}
```

**Why it looks reasonable.** One bean to autowire. One import.

**What it costs.** `booking` wanted to know who is acting, and now compiles against credential resets and
role grants. Every signature change in any of them rebuilds and re-reviews every consumer, and the module's
real seams are invisible — you cannot tell from the outside that resolving a principal and resetting a
password are unrelated.

**Instead:** narrow ports named for the question. `PrincipalContext` has two methods and answers one thing.

### 3 · The `shared` module as a dumping ground

```
shared/
  util/StringUtils.java        BookingHelper.java        Constants.java
```

**Why it looks reasonable.** Two modules needed it, and `shared` is where common things go.

**What it costs.** `shared` is depended on by 25 modules, so it is the most expensive place in the reactor
to put anything. `BookingHelper` there means every module rebuilds when booking's rules change, and a
reviewer cannot tell who owns it. A grab-bag named `util` has no membership test, so nothing is ever
rejected from it.

**Instead:** apply the test — *is it machinery every module needs?* `BaseEntity` and `Times` pass.
`BookingHelper` is booking's, however many modules call it; if a second genuinely needs it, that is a port.

### 4 · The foreign key across a boundary

```sql
ALTER TABLE staff_operators
    ADD CONSTRAINT fk_operator FOREIGN KEY (operator_uid) REFERENCES operators (uid);  -- tenancy's table
```

**Why it looks reasonable.** Referential integrity is good. A dangling handle is a real bug.

**What it costs.** `identity-access` is wave 2 and `tenancy` is wave 4 — this constraint requires the later
module's table to exist before the earlier one can migrate, which inverts the build order. It also welds two
migration histories together: `tenancy` can no longer alter its own key without a coordinated change.

**Instead:** ③ bare handle, failing closed where it is resolved. **And take the constraints still available
to you** — `staff_operators` cannot have an FK to `operators`, but it has a composite FK *within*
`identity-access` that makes a cross-company membership impossible. Losing the arrow to another module is not
losing constraints altogether.

### 5 · Authority read from the request body

```java
public record CreateBookingRequest(UUID agentUid, UUID tripUid, List<String> seats) { }
//                                 ^^^^^^^^^^^^ who the caller says they are
```

**Why it looks reasonable.** The client knows which agent it is; the server would only look it up again.

**What it costs.** One agent sells under another's identity by editing one field — and every downstream
record, commission line and audit row attributes it to the wrong person. It is not a bug that surfaces; it
surfaces as *someone else's* sales figures.

**Instead:** read it from the `Principal`. Where a caller genuinely must name something, make it a **query
parameter validated against their own scope**, so it selects among things they already reach and can never
widen them — `OperatorScope.requireTarget` is the worked example.

### 6 · The entity returned across a boundary

```java
public interface StaffLookup {
    StaffIdentity findByUid(UUID uid);       // the entity itself
}
```

**Why it looks reasonable.** The fields are the same ones the view would have. Writing a second type feels
like duplication.

**What it costs.** Three things at once. The caller can now reach `internal` types through the entity's
associations, so the boundary rule is bypassed without an import that names anything. Adding a column adds it
to the wire silently — including the day the column is a credential hash. And a lazy association serialises
at whatever moment the writer touches it, outside any transaction.

**Instead:** a view record with an `of(entity)` projection. The fields overlapping today is not the point;
the point is that they diverge the first time one must not be shown.

### 7 · Publishing to the broker inside the transaction

```java
bookingRepository.save(booking);
eventPublisher.send("booking.confirmed", payload);   // network call, mid-transaction
```

**Why it looks reasonable.** It is one line and it is right there next to the write.

**What it costs.** The two cannot commit together. If the transaction rolls back after the send, **the
broker has been told about a sale the database does not have** — an SMS to the passenger, a fiscal receipt
and a regulator submission for a ticket nobody holds. It also puts a network call inside a transaction
holding a contended seat row.

**Instead:** ④, `outbox.enqueue(...)`, which is a row in the same transaction.

### 8 · Promoting to `api-contracts` on first use

```java
// api-contracts/.../dto/BookingView.java     ← used by exactly one module
```

**Why it looks reasonable.** It appears on the wire, and the doc says wire types go here.

**What it costs.** Appearing on the wire is necessary, not sufficient. `api-contracts` is depended on by 26
modules, so a type here turns a one-module change into a full-reactor rebuild and a shared review surface —
paid by a type exactly one module uses.

**Instead:** keep it in `internal/domain/dto` until a **second** consumer appears, and move it in the commit
that introduces that consumer.

## How each channel is tested

| Channel | A test must assert | What fails silently if untested |
|---|---|---|
| ① published port | the port refuses as documented, not merely that it returns | a caller proceeds on a null actor because nobody checked the 401 path |
| ② inbound port | the fail-closed default is what runs when no implementation is present | the context starts, the port is absent, and the feature quietly does nothing |
| ③ uid handle | a **dangling** handle produces a refusal, not an exception or an empty result | a stale uid reads as "no restriction" and widens access |
| ④ outbox event | the event row rolls back with the business write | broker told about a sale the database rolled back |
| ⑤ pass-through | the enforcer refuses when handed the boundary value, and **has no other source for it** | the enforcer grows a default and the rule silently has two homes |
| ⑥ snapshot | changing the source afterwards does **not** change the artefact | a "helpful" sync job rewrites history and nobody notices |

Two of these are easy to write badly. **③ is usually tested with a valid handle**, which proves nothing —
the case that matters is the dangling one. **⑥ is usually tested by reading the snapshot back**, which also
proves nothing; the test has to *change the source* and assert the artefact did not move.

### What has no automated enforcement

| Rule | Enforced by | Gap |
|---|---|---|
| no cross-module table access | **nothing** | rules read bytecode; SQL strings are invisible |
| adapters point inward | the DAG data, plus the generic rule | a commit editing pom **and** `ModuleCatalog.DAG` together passes |
| authority not from a body | **nothing** | a `UUID` field looks like every other field |
| snapshot never updated | **nothing** | no constraint expresses "insert-only column" |
| promote on second use | **nothing** | review only |

Five rules, one of them partly enforced. **That is the honest picture**, and it is the argument for the
review checklist rather than for trusting a green build.

## Decision table

| I need… | Do this | Not this |
|---|---|---|
| one field of theirs, for display | a read-side lookup port returning names; keep it off the write path | a join, or holding their entity |
| to check a permission | the constant from `identity-access.Permissions`, via the `@perm` bean name | writing the code as a string literal, or reading roles yourself |
| to store a reference to their row | their `uid`, as a bare column | a foreign key, or their entity |
| them to do something, now | call their published port | writing to their tables |
| to say something happened | `enqueue()` to the outbox, in your transaction | calling every interested module in turn |
| a constant both sides use | `api-contracts` if it hits the wire, `shared` if it is machinery | duplicating it, or reaching into their `internal` |
| something from a module that already depends on me | declare an inbound port on my side; let them implement it | adding the reverse edge — that is a cycle |
| B to enforce a limit that C decides | read it from C and pass it to B — ⑤ | an edge B → C, which gives the rule a second home |
| what a ticket or receipt says to stay true | copy the display values onto the row — ⑥ | joining at read time, so last quarter's ticket reprices itself |
| to know whether a value may be passed in | ask whether it could have come from a request; if so, it may not | passing it anyway, because the frames in between launder nothing |

## What enforces this

| Rule | Catches |
|---|---|
| Maven | An import of a module outside your **transitive** closure. Weaker than it sounds: every module declares `shared` and `api-contracts`, and most declare `identity-access`, so much of the reactor is reachable transitively and javac compiles it happily. The bytecode rule below is what actually catches those. |
| `ModuleDependencyTest` (pom ↔ DAG) | An edge nobody decided on, or an architecture claim the build does not have. |
| `ModuleDependencyTest` (bytecode) | An undeclared edge that Maven's transitive classpath would otherwise permit silently. |
| `ModuleBoundaryTest` | Anything outside a module reaching into its `internal/`. |
| `AnalysisClasspathTest` | A module joining the reactor without joining the analysis — where every rule above reports green while checking nothing. |

**And the gap:** none of them read SQL. Cross-module table access is invisible to all of it — see the
anti-patterns above for the full list of rules that rest on review rather than on a build.

---

## Keeping this document honest

Most of what is described here is a contract for code that is not written. That is the right way round —
these decisions are cheaper to make once, now, than to reverse across seventeen modules later — but it has a
maintenance cost: **an intention written in the present tense becomes a lie the moment somebody trusts it.**

Two rules for editing this file:

1. **Mark what does not exist.** Every aspirational type, port and error code above carries a note saying so.
   When one gets built, delete its note in the same commit.
2. **Do not describe enforcement you have not checked.** This document claimed a hand-written ArchUnit rule
   for adapters that was never written, and claimed Maven catches undeclared imports that it compiles
   happily. Both survived because they were plausible. Read the test before writing that a test exists.
