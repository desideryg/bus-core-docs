# 22 · Implementation plan

*Assumes [00-glossary.md](00-glossary.md), [20-module-catalog.md](20-module-catalog.md),
[21-inter-module-communication.md](21-inter-module-communication.md).*

The order the 27 modules get built, derived from the dependency DAG rather than chosen.

> **This table is generated.** Regenerate it with `python tools/waves.py` after any change to the DAG. If
> the output differs from what is written here, this document is out of date — regenerate, do not edit by
> hand. A build order maintained separately from the DAG stops matching it the first time an edge is added,
> and a stale build order is worse than none: it is confidently wrong.

## Waves

A module's **wave** is one more than the wave of its latest dependency; the two leaves are wave 0.
So **every module within a wave can be built in parallel**, and the number of waves is the critical path.

| Wave | Modules | Unblocks |
|---:|---|---|
| **0** | `api-contracts` · `shared` | api-contracts→25, shared→25 |
| **1** | `identity-access` · `quota` · `accounting-ledger` · `exchange-rate` · `reporting` | identity-access→16, quota→1 |
| **2** | `network` · `promotions` · `storage` | network→7, promotions→2, storage→1 |
| **3** | `documents` | documents→5 |
| **4** | `tenancy` · `fleet` · `customer` | tenancy→7, fleet→4, customer→1 |
| **5** | `agent` · `staff` | agent→6, staff→1 |
| **6** | `scheduling` · `wallet-ledger` | scheduling→6, wallet-ledger→3 |
| **7** | `fare` | fare→3 |
| **8** | `seat-inventory` | seat-inventory→2 |
| **9** | `booking` | booking→4 |
| **10** | `payment-settlement` · `charter` | payment-settlement→3 |
| **11** | `notification` · `payment-gateway-adapter` | notification→2 |
| **12** | `fiscal-adapter` · `uts-adapter` | — |

27 modules, 13 waves.

## The shape of it

```
WAVE 0 ── shared ─────────────── api-contracts
             └───────────┬───────────┘
                         ▼
WAVE 1 ── identity-access ⭐16   quota   exchange-rate   reporting   accounting-ledger
                         │        │     └──── block nothing; build any time ────┘
            ┌────────────┼────────────┐
            ▼            ▼            ▼
WAVE 2 ── network ⭐7  promotions   storage
                                      │
                                      ▼
WAVE 3 ──────────────────────── documents ⭐5        ← the chokepoint
                                      │
            ┌─────────────────────────┼───────────┐
            ▼                         ▼           ▼
WAVE 4 ── tenancy ⭐7               fleet       customer
            │                         │
            ├───────────┐             │
            ▼           ▼             │
WAVE 5 ── agent ⭐6    staff          │
            │           │             │
            ▼           ▼             │
WAVE 6 ── wallet-ledger  scheduling ⭐6 ◄┘
                         │
                         ▼
WAVE 7 ───────────────  fare
                         │
                         ▼
WAVE 8 ────────────  seat-inventory
                         │
                         ▼
WAVE 9 ──────────────  booking ⭐4      ← also needs quota, promotions, customer, network, tenancy
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
WAVE 10 ─ payment-settlement       charter
            │
            ├─────────────────────────┐
            ▼                         ▼
WAVE 11 ─ notification        payment-gateway-adapter
            │
            ├─────────────────────────┐
            ▼                         ▼
WAVE 12 ─ fiscal-adapter          uts-adapter
```

⭐ = modules blocked downstream.

## Critical path

```
api-contracts → identity-access → storage → documents → tenancy → staff
  → scheduling → fare → seat-inventory → booking → payment-settlement
  → notification → uts-adapter
```

**13 of 27 modules sit on it.** Every step is a hard sequence; nothing shortens it, and slipping any one of
them slips everything after it.

## What the graph says about scheduling work

**`documents` is the chokepoint.** One module in wave 3, with five waiting on it — `tenancy`, `fleet`,
`customer`, and transitively `agent` and `staff`. It is small (a type catalog plus an owner-typed store) but
it gates the whole tenant and fleet tier. Slipping it stalls waves 4 through 6.

Its position is a direct consequence of the rule in [20-module-catalog.md](20-module-catalog.md) that
`documents` depends on no owner module. That absence is what keeps the DAG acyclic; the price is that it
sits early and everything owning documents queues behind it.

**Four modules are unblocked at any time.** `quota`, `exchange-rate`, `reporting` and `accounting-ledger`
depend only on the two leaves and block nothing. They are the work to hand someone when the critical path is
contended. Note `quota` is needed by `booking` at wave 9, so it must land before then; the other three never
block anything.

**Waves 7–9 are the waist.** `fare → seat-inventory → booking`, strictly serial, one module each. No
parallelism is available there — adding people does not shorten it.

**`charter` looks heavy and is not.** Nine declared dependencies, but it blocks nothing: a leaf at wave 10,
deferrable indefinitely.

**Adapters are last and independent of each other.** `payment-gateway-adapter`, `fiscal-adapter` and
`uts-adapter` block nothing and can be built in any order once their inward port exists.

## Phasing

| Phase | Waves | Delivers | Modules |
|---|---|---|---:|
| **1 · Foundation** | 0–3 | Somebody can log in. Files can be stored and typed. | 11 |
| **2 · Reference data** | 4–6 | Tenants, fleet, crew, routes, timetable, selling agents, wallets. | 7 |
| **3 · The sale** | 7–9 | Price → seat → booking. The revenue path. | 3 |
| **4 · Money and externals** | 10–12 | Settlement, notification, gateway, regulator, charter. | 6 |

**Nothing is billable until phase 3 completes** — 21 modules of groundwork before a ticket can be sold.
That is worth stating plainly at the start rather than discovering at wave 7.

## Two rules that apply throughout

**A module joins the deployable when its first slice lands, not when its directory is created.** Adding the
`<dependency>` to `services/bus-core` is the last step of a slice. See
[20-module-catalog.md](20-module-catalog.md).

**Wave order is not slice order.** A wave says when a module *may* start, not that it must be finished
before the next wave begins. A module's first vertical slice is usually enough to unblock its dependants —
`documents` needs its catalog and attach path to unblock `fleet`, not its full verification workflow.
