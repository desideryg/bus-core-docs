# 22 · Implementation plan

*Assumes [00-glossary.md](00-glossary.md), [20-module-catalog.md](20-module-catalog.md),
[21-inter-module-communication.md](21-inter-module-communication.md).*

The order the 27 modules get built, derived from the dependency DAG rather than chosen.

> **This table is generated.** Regenerate it with `python tools/waves.py` after any change to the DAG. If
> the output differs from what is written here, this document is out of date — regenerate, do not edit by
> hand. A build order maintained separately from the DAG stops matching it the first time an edge is added,
> and a stale build order is worse than none: it is confidently wrong.
>
> **⚠ This table is currently ahead of the code.** It reflects a decided change — `notification` re-scoped to
> a thin wave-1 transport that depends only on `api-contracts`. `ModuleCatalog.java` still declares the old
> edges, so running `waves.py` today reproduces the *previous* layout. Land the one-line DAG change, then
> regenerate and delete this note.

## Waves

A module's **wave** is one more than the wave of its latest dependency; the two leaves are wave 0.
So **every module within a wave can be built in parallel**, and the number of waves is the critical path.

| Wave | Modules | Unblocks |
|---:|---|---|
| **0** | `api-contracts` | api-contracts→26 |
| **1** | `shared` · `notification` | shared→24, notification→2 |
| **2** | `identity-access` · `quota` · `accounting-ledger` · `exchange-rate` · `reporting` | identity-access→15, quota→1 |
| **3** | `network` · `promotions` · `storage` | network→6, promotions→2, storage→1 |
| **4** | `documents` | documents→5 |
| **5** | `tenancy` · `fleet` · `customer` | tenancy→6, fleet→4, customer→1 |
| **6** | `agent` · `staff` | agent→5, staff→1 |
| **7** | `scheduling` · `wallet-ledger` | scheduling→5, wallet-ledger→2 |
| **8** | `fare` | fare→3 |
| **9** | `seat-inventory` | seat-inventory→2 |
| **10** | `booking` | booking→3 |
| **11** | `payment-settlement` · `charter` · `uts-adapter` | payment-settlement→2 |
| **12** | `fiscal-adapter` · `payment-gateway-adapter` | — |

27 modules, 13 waves.

> **`notification` moved to wave 1.** It used to sit at wave 12 — last but the adapters — because it depended
> on the entire sale path to *render* rich messages. Re-scoped to a **thin transport** (channels, encrypted
> credentials, dispatch of an already-rendered message) it depends only on `api-contracts`, so any module
> from wave 2 on — `identity-access` included, for the reset-invitation email — can hand it something to
> send. Composing the *content* of a sale message (reading a booking to build its SMS) is a separate, later
> concern that still announces over the outbox; see
> [21-inter-module-communication.md](21-inter-module-communication.md), which still describes the old
> late-notification model and needs reconciling.

## The shape of it

```
WAVE 0 ─────────────────────── api-contracts ⭐26      pure types, no dependency at all
                          ┌───────────┴───────────────┐
                          ▼                           ▼
WAVE 1 ─────────────── shared ⭐24              notification ⭐2   thin transport: channels + dispatch
                          │
            ┌─────────────┼───────────────────────────┐
            ▼             ▼                           ▼
WAVE 2 ── identity-access ⭐15   quota   exchange-rate   reporting   accounting-ledger
                         │        │     └──── block nothing; build any time ────┘
            ┌────────────┼────────────┐
            ▼            ▼            ▼
WAVE 3 ── network ⭐6  promotions   storage
                                      │
                                      ▼
WAVE 4 ──────────────────────── documents ⭐5        ← the chokepoint
                                      │
            ┌─────────────────────────┼───────────┐
            ▼                         ▼           ▼
WAVE 5 ── tenancy ⭐6               fleet       customer
            │                         │
            ├───────────┐             │
            ▼           ▼             │
WAVE 6 ── agent ⭐5    staff          │
            │           │             │
            ▼           ▼             │
WAVE 7 ── wallet-ledger  scheduling ⭐5 ◄┘
                         │
                         ▼
WAVE 8 ───────────────  fare
                         │
                         ▼
WAVE 9 ────────────  seat-inventory
                         │
                         ▼
WAVE 10 ─────────────  booking ⭐3      ← also needs quota, promotions, customer, network, tenancy
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
WAVE 11 ─ payment-settlement   charter   uts-adapter
            │
            ├─────────────────────────┐
            ▼                         ▼
WAVE 12 ─ fiscal-adapter        payment-gateway-adapter
```

⭐ = modules blocked downstream.

## Critical path

```
api-contracts → shared → identity-access → storage → documents → tenancy → staff → scheduling → fare → seat-inventory → booking → payment-settlement → payment-gateway-adapter
```

**13 of 27 modules sit on it.** Every step is a hard sequence; nothing shortens it, and slipping any one of
them slips everything after it. `notification` used to sit on this path (a regulator adapter waited on it);
pulling it to wave 1 took it off, and the critical path now ends at the gateway adapter.

## What the graph says about scheduling work

**`documents` is the chokepoint.** One module in wave 4, with five waiting on it — `tenancy`, `fleet`,
`customer`, and transitively `agent` and `staff`. It is small (a type catalog plus an owner-typed store) but
it gates the whole tenant and fleet tier. Slipping it stalls waves 5 through 7.

Its position is a direct consequence of the rule in [20-module-catalog.md](20-module-catalog.md) that
`documents` depends on no owner module. That absence is what keeps the DAG acyclic; the price is that it
sits early and everything owning documents queues behind it.

**Four modules are unblocked at any time.** `quota`, `exchange-rate`, `reporting` and `accounting-ledger`
depend only on the two leaves and block nothing. They are the work to hand someone when the critical path is
contended. Note `quota` is needed by `booking` at wave 10, so it must land before then; the other three never
block anything.

**Waves 8–10 are the waist.** `fare → seat-inventory → booking`, strictly serial, one module each. No
parallelism is available there — adding people does not shorten it.

**`charter` looks heavy and is not.** Nine declared dependencies, but it blocks nothing: a leaf at wave 11,
deferrable indefinitely.

**Adapters are last and independent of each other.** `payment-gateway-adapter`, `fiscal-adapter` and
`uts-adapter` block nothing and can be built in any order once their inward port exists.

## Phasing

| Phase | Waves | Delivers | Modules |
|---|---|---|---:|
| **1 · Foundation** | 0–4 | Somebody can log in, files can be stored and typed, and messages can be sent. | 12 |
| **2 · Reference data** | 5–7 | Tenants, fleet, crew, routes, timetable, selling agents, wallets. | 7 |
| **3 · The sale** | 8–10 | Price → seat → booking. The revenue path. | 3 |
| **4 · Money and externals** | 11–12 | Settlement, gateway, regulator, charter. | 5 |

**Nothing is billable until phase 3 completes** — 22 modules of groundwork before a ticket can be sold.
That is worth stating plainly at the start rather than discovering at wave 7.

## Two rules that apply throughout

**A module joins the deployable when its first slice lands, not when its directory is created.** Adding the
`<dependency>` to `services/bus-core` is the last step of a slice. See
[20-module-catalog.md](20-module-catalog.md).

**Wave order is not slice order.** A wave says when a module *may* start, not that it must be finished
before the next wave begins. A module's first vertical slice is usually enough to unblock its dependants —
`documents` needs its catalog and attach path to unblock `fleet`, not its full verification workflow.
