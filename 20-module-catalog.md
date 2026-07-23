# 20 · Module catalog and the DAG

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[11-naming.md](11-naming.md).*

27 modules. **Every one is currently an empty skeleton** — a pom and two `package-info.java` files. They
build as reactor jars so they can be implemented; only `shared` and `api-contracts` are assembled into the
deployable so far.

## The catalog

### Foundations

| Module | Depends on | Owns |
|---|---|---|
| `api-contracts` | *nothing* | The error catalog, the response envelope, permission constants, cross-module wire enums. No framework dependency of any kind, so the same types can back a generated client SDK. |
| `shared` | `api-contracts` | Cross-cutting kernel: base entity, audit, outbox/messaging, paging, time, translation, logging. |

`shared → api-contracts` is the one edge here, and it exists because **shared must be able to refuse**.
Paging validation rejects an unusable sort expression, and it does so with the one error model rather than a
JDK exception the web layer would have to blanket-map to 400 — a mapping that would quietly turn ordinary
programming mistakes into 400s for callers instead of 500s in the log.

### Tier 1 — identity, storage, and reference data

| Module | Owns |
|---|---|
| `identity-access` | Staff/agent/machine authentication, the permission catalog, the operator scope. |
| `storage` | Object/blob store behind an S3-compatible provider port. |
| `documents` | What a file *means*: owner, type, expiry, verification. Layers on top of `storage`. |
| `tenancy` | The tenant hierarchy Company → Brand → Operator → Branch. |
| `network` | Stations, routes, ordered route stops. |
| `fleet` | Vehicles, seat layouts, and the asset lifecycle around them. |
| `staff` | Operator HRMS: employees, drivers, conductors, departments, payroll. |
| `quota` | Sub-route and agent seat-allocation yield rules. No HTTP surface. |
| `exchange-rate` | FX rates and currency conversion. No HTTP surface. |
| `promotions` | Booking discounts; a frozen discount line the sale snapshots. |
| `reporting` | Rebuildable read models. A leaf; never a source of truth. |
| `accounting-ledger` | Double-entry general ledger. |
| `customer` | Passenger master identity — the golden record. Distinct from `identity-access`. |

### Tier 2 — selling identity, timetable, price, seat

| Module | Owns |
|---|---|
| `agent` | Selling authority: which agents sell what, for whom, under what limits. Fails closed. |
| `scheduling` | Scheduled trips: lifecycle, assignment, readiness, seat materialisation. |
| `fare` | Fare calculation and snapshotting. No HTTP surface. |
| `seat-inventory` | Seat availability, locks, holds — the double-sell arbiter. |
| `wallet-ledger` | Agent wallets, immutable ledger entries, commission. Balance is derived, never stored. |

### Tier 3 — the sale

| Module | Owns |
|---|---|
| `booking` | Booking lifecycle and idempotent creation. Coordinates; does not decide. |
| `payment-settlement` | Payment/settlement state and the gateway port the adapter implements. |
| `notification` | Channel providers, encrypted credentials, dispatch. |

### Adapters — point inward, nothing depends on them

| Module | Owns |
|---|---|
| `payment-gateway-adapter` | Anti-corruption layer over a payment vendor; signed callbacks. |
| `uts-adapter` | Transport-regulator submission behind an inward port. |
| `fiscal-adapter` | Revenue-authority fiscal receipting behind an inward port. |
| `charter` | Whole-bus hire: request, quote, accept, check-in, manifest. |

## The dependency DAG

This is the authoritative edge set. It lives in
`architecture-tests/…/archtests/ModuleCatalog.java` and in each module's pom, and the build fails if the
two disagree in either direction.

| Module | Deps | Declares |
|---|---:|---|
| `api-contracts` | 0 | — |
| `shared` | 1 | api-contracts |
| `identity-access` | 2 | shared, api-contracts |
| `storage` | 3 | + identity-access |
| `documents` | 4 | + storage |
| `tenancy` | 4 | + documents |
| `network` | 3 | + identity-access |
| `fleet` | 4 | + documents |
| `staff` | 5 | + tenancy, documents |
| `quota` | 2 | — |
| `exchange-rate` | 2 | — |
| `promotions` | 3 | + identity-access |
| `reporting` | 2 | — |
| `accounting-ledger` | 2 | — |
| `customer` | 4 | + identity-access, documents |
| `agent` | 6 | + tenancy, network, documents |
| `scheduling` | 7 | + network, fleet, tenancy, staff |
| `fare` | 7 | + network, scheduling, tenancy, fleet |
| `seat-inventory` | 8 | + agent, scheduling, network, fare, fleet |
| `wallet-ledger` | 5 | + agent, tenancy |
| `booking` | 12 | + agent, scheduling, fare, seat-inventory, quota, network, tenancy, promotions, customer |
| `payment-settlement` | 8 | + booking, agent, wallet-ledger, scheduling, promotions |
| `notification` | 10 | + booking, payment-settlement, wallet-ledger, scheduling, network, tenancy, agent |
| `payment-gateway-adapter` | 4 | shared, api-contracts, payment-settlement, wallet-ledger |
| `uts-adapter` | 4 | shared, api-contracts, notification, booking |
| `fiscal-adapter` | 4 | shared, api-contracts, notification, payment-settlement |
| `charter` | 9 | booking, scheduling, seat-inventory, fare, fleet, network, agent (+ the two leaves) |

### The absence that makes it work

**`documents` depends on no owner module** — not `fleet`, not `tenancy`, not `agent`, not `staff`, not
`customer`. It holds `ownerUid` as a bare handle and resolves it against nothing.

That absence is precisely what lets all five of those modules depend on `documents` without a cycle. Adding
an owner-module edge here to "look up an owner's name" would make that impossible forever. If a read-side
label is ever wanted, it belongs in the owner module's own view.

The same shape appears twice more: `promotions` depends on no sale-path module, which keeps
`booking → promotions` acyclic; and `customer` depends on no sale-path module, which keeps
`booking → customer` acyclic.

## Adding a module

Seven files change. All seven, or the module is half-present in a way that stays hidden for months:

1. `pom.xml` (root) — `<module>modules/<name></module>`
2. `pom.xml` (root) — a `dependencyManagement` entry pinning `tz.co.otapp.buscore:<name>:0.1.0-SNAPSHOT`
3. `modules/<name>/pom.xml` — parent, internal edges, starters
4. `.../<pkg>/package-info.java` — what the module is
5. `.../<pkg>/internal/package-info.java` — the hiding notice
6. `architecture-tests/pom.xml` — a `<dependency>` with `<version>${project.version}</version>`
7. `ModuleCatalog.DAG` — the module and its exact edge set

**6 and 7 are the ones people forget**, and the build catches both: `AnalysisClasspathTest` fails on a
missing 6, `ModuleDependencyTest.every_reactor_module_is_in_the_dag` on a missing 7. Keep the
`<version>${project.version}</version>` element on 6 — `AnalysisClasspathTest` matches that exact shape when
it parses the pom.

## Adding an edge

Change **the module's pom and `ModuleCatalog.DAG` in the same commit**, with the reason in the PR.

An edge in the pom but not the DAG is a dependency nobody decided on — it arrived in some commit and no one
had to argue for it. An edge in the DAG but not the pom is a lie: the architecture claims a relationship the
build does not have.

Two shapes to prefer, both of which keep the DAG acyclic:

- **Point adapters inward.** An adapter implements a port owned by the module it names, and nothing depends
  on the adapter.
- **Hold uids, not foreign keys.** A module storing another's identifier as a bare handle, resolving it
  against nothing, needs no edge at all.
