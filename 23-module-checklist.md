# 23 · The module checklist

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[11-naming.md](11-naming.md), [12-api-conventions.md](12-api-conventions.md),
[20-module-catalog.md](20-module-catalog.md),
[21-inter-module-communication.md](21-inter-module-communication.md),
[22-implementation-plan.md](22-implementation-plan.md).*

The other documents say what the rules are. **This one is the list you walk before saying a module or a
slice is done.**

## The two ways a module hurts the system

A module is 27th of 27. Almost nothing you build stands alone, and almost nothing fails alone either. There
are exactly two ways your module damages everything around it, and they are not equally dangerous.

**It is wrong.** A refusal that should be a permit, a total that should be a sum. This is the good case: the
failure is in your module, it is yours to fix, and a test can find it.

**It is inconsistent with what it told everyone else.** Your published record gained a component, so every
consumer's compile breaks. Your migration never ran, so the table is absent in one environment and present
in another. Your permission was declared and never seeded, so a route refuses every caller alive and no test
notices. **These do not surface where they were caused.** They surface weeks later, in somebody else's
module, as a failure that reads like an outage rather than like a mistake — and the person holding it has no
path back to the commit that caused it.

The second class is what this checklist exists for. It is not a quality bar; it is a *blast-radius* bar.

```
   a wrong module          an inconsistent module
   ──────────────          ──────────────────────
   fails here              fails somewhere else
   fails now               fails when an unrelated slice lands
   fails loudly            often fails silently, or intermittently
   your test catches it    no test is even watching
```

## Partial is expected

**You are not required to finish a module.** The build order in
[22-implementation-plan.md](22-implementation-plan.md) is waves, and a wave-2 module is depended on by
sixteen others long before it is complete. `identity-access` was useful to the whole system after slice 1 of
12, and is still only 7 of 12 today.

What you are required to do is leave it **consistent at every commit** — which is a different and much
weaker condition than complete, and the next section defines it exactly. A module that does a third of its
job and refuses the rest is a good citizen. A module that does a third of its job and *permits* the rest is
a landmine with a delay on it.

## How to use this

Seven gates, in order. Each is a tick-list of checks you can actually run — a command, a grep, a file to open
— rather than a sentiment you can agree with and skip.

| Gate | Answers | Skipped ⇒ |
|---|---|---|
| **0 · Specify, then place** | What is this module, what are its entities and edge cases, and where does it sit? | an entity model discovered while coding; a cycle; "empty means all" shipped |
| **1 · Structure** | Is it laid out so the boundary rules can see it? | internals leak; the arch tests pass while checking nothing |
| **2 · Persistence** | Does the schema exist, run, and agree with the entities? | migrations that never run, in one environment only |
| **3 · Boundaries** | Is the published surface minimal and honest? | consumers welded to your internals |
| **4 · HTTP surface** | Are the envelope, audience and permissions right? | a route that silently refuses everyone forever |
| **5 · Tests** | Is everything that fails *open* covered? | a guard that reads as enforced and is not |
| **6 · Handover** | Can the next person tell what is done from what is stubbed? | the next slice builds on something that was never there |

**Gate 0 is the one people skip and the only one that cannot be fixed later without a rewrite.** Every other
gate catches a mistake inside your module. Gate 0 catches the mistake that puts your module in the wrong
place in the graph, and by the time that shows up, sixteen modules have compiled against it.

---

## Partial is fine. Inconsistent is not.

The gates below are the walk. This section is the standard they enforce, and the reason the checklist is not
"finish the module". Nobody finishes a module here. `identity-access` is seven slices into twelve; **24 of
the 27 modules are a pom and two `package-info.java` files and nothing else** — open `modules/booking/` and
that is the whole module. The build order runs to fourteen waves. "Partly built" is the normal state, and
most modules will be in it for months. So the rule has to be that at every commit the parts of a module
**agree with each other**, whether or not there are many of them.

### The two inert lines

Two pieces of `identity-access` did nothing at all for several slices. One is the best thing in the module.
The other was a 500 waiting for a date.

```
  slice      1     2     3     4     5     6     7
             │     │     │     │     │     │     │
  Audience.AGENT ────────●═════════════════════════►  slice 7: Set.of(PrincipalType.AGENT)
             │     │     │                       │    the agent surface arrived ALREADY CLOSED
             │     │     └ reserved as Set.of()  │    — nothing to retrofit across 57 routes
             │     │       nobody is permitted   │
             │     │                             │
  tenancy claim ───●╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌✗    first agent login: 500
             │     │                             │    JwtClaimsSet rejects a null value
             │     └ written slice 2 as          │
             │       tenancy == null ? null : …  │
             │       never executed until here ──┘
```

Same repository, same habit of writing a thing before anything needs it, opposite outcomes. The difference
is not *early versus late*. It is what the inert state **was**: `Audience.AGENT` permitted `Set.of()` —
**nobody**, so inert meant *refusing*; `JwtService` wrote `null` into a claims builder that rejects nulls, so
inert meant *unproven*. **A gap that refuses is safe at any degree of incompleteness. A gap that merely has
not run yet is a defect with a start date.** Everything below is that sentence made testable.

### What "consistent" means, precisely

Four agreements. A commit is consistent when all four hold; a partial module can hold all four with almost
nothing in it.

| Agreement | Holds when | Breaks as |
|---|---|---|
| **Code with itself** | every branch is exercised by a test, or unreachable by a *type or a constraint* | a latent failure that fires on somebody else's commit, weeks later |
| **Code with prose** | nothing named in a comment, javadoc, migration or doc is missing from the tree | a reviewer trusts an invariant that nothing enforces |
| **Surface with the future** | the published shape is whole; only the contents are partial | a widening every consumer has to absorb, in one commit |
| **Gap with the caller** | every unimplemented path refuses, with a code, and the gap is written down | the gap is discovered as unauthorised access, not as a 501 |

Cross those with complete/partial and only one cell is dangerous: **partial *and* inconsistent** — the
landmine, because it is the only state where the build is green and the module looks finished from outside,
yet it fails on the commit that finishes it, written by someone else, months later. The six rules make each
agreement testable.

### Rule 1 · An unimplemented path refuses. It never permits.

The reserved audience is the shape to copy — slice 3, `Audience.java`:

```java
STAFF("/admin/v1/", Set.of(PrincipalType.STAFF)),
AGENT("/agent/v1/", Set.of());          // reserved: permits nobody
```

Nothing served `/agent/v1/**` for four slices. The entry earns its place anyway, because the alternatives
fail open: **no `AGENT` constant** → `Audience.of()` returns null, the filter has no opinion, a staff token
reaches the agent surface; **`Set.of(STAFF)`** → the placeholder becomes the permission and nobody narrows
it; **`EnumSet.allOf(…)`** → "later" never arrives with a smaller set than already shipped. Only `Set.of()`
means *decided: nobody*, so slice 7 changed one literal and the surface was never open. Leaving it out looks
right — an entry permitting nobody reads as dead code — but **absent means "not audience-scoped" and empty
means "refused"**; deleting the constant removes a *closure*, not a check. The reference implementation did
the retrofit instead, keeping agents off the staff surface with a *tenancy* check doing an audience check's
job across 57 routes. The shape recurs wherever a decision is not yet available: `OperatorScope.filter()`'s
nil-uuid sentinel (**empty never means "all"**); `RootBootstrap` creating nothing on a blank
`identity.bootstrap.root.password` rather than a shared default; and — aspirational, no instance yet — a
fail-closed `503` bean for an unimplemented port.

**The test.** For every path your module does not implement yet, name the response. If the answer is "it does
not come up", the path is fail-open and you have not noticed.

### Rule 2 · The published shape is whole even when the contents are not.

`PrincipalType` held one constant for six slices. A one-element enum invites replacement by a boolean, but it
stays because `Principal` is a compile-time contract for the 16 modules that will depend on `identity-access`,
and **the two ways of widening it later have very different blast radii:**

| Later change | What breaks | Where |
|---|---|---|
| append an enum constant | an exhaustive `switch` with no `default` | the few sites that switch — a compiler error locates them |
| add a record component | **every** `new Principal(...)`, every deconstruction pattern | every consumer, in one commit |

So shape is settled early, contents filled in late. `Principal` *did* widen twice (slice 1 `(uid, type)`;
slice 2 added `tenancy`, `permissions`; slice 5a added `operatorUids`) — affordable **only because the
consumer set was empty**; 24 modules still have no code that could break. The rule bites from the first
commit in which a second module compiles against a published type. The corollary: a published type must be
**total about what it will never carry**. From slice 7, `Principal`'s compact constructor rejects an agent
carrying permissions, a tenancy or operators — agent authority lives in the `agent` module, so an agent's
permission set is empty *permanently*. That pays off at the token boundary, where `JwtService.parse` catches
`IllegalArgumentException` and returns empty, so a forged token claiming `AGENT` with a populated `prm` claim
is unusable rather than privileged.

**The test.** Ask what a consumer would change if you completed this type next quarter. If it touches their
call sites rather than their `switch` statements, the shape is not finished.

### Rule 3 · If you name a test, a class or a rule, it exists.

Three real violations here, all surviving because **a plausible name reads as a citation**, which stops a
reviewer looking for the risk:

- **`PermissionCatalogTest`.** From slice 2 to 5b, `Permissions.java` and `R__seed_rbac.sql` both cited a
  class of that name holding the constants and the seed to each other. **Nobody ever wrote it** — and its
  invariant is the worst to imagine enforcement for (a declared-but-unseeded permission refuses everyone
  forever, silently; Gate 4). Both comments now name `RbacIntegrationTest` at
  `services/bus-core/src/test/java/tz/co/otapp/buscore/RbacIntegrationTest.java`, whose
  `catalog_agrees_in_both_directions` compares `Permissions.ALL` against `SELECT code FROM permissions` both
  ways.
- **The adapter rule.** Doc 21 claimed a hand-written ArchUnit rule keeping adapters undependable. There is
  none — the property holds only because no module's `ModuleCatalog.DAG` entry lists an adapter.
- **`api-contracts`'s `security` package.**
  `modules/api-contracts/src/main/java/tz/co/otapp/buscore/apicontracts/security/package-info.java` says the
  permission constants "live here". They do not — they are in `identityaccess.Permissions`. **The fix is to
  delete the package, not move the constants:** they must agree with a seed in `identity-access`, and
  splitting them across a boundary puts the test holding them together on the wrong side of it.

**The test.** Grep for it. If a comment, javadoc, migration header or document names a type, test, column,
rule or package, that name must resolve in the tree at that commit. If it will exist later, say so in the
future tense and mark it — as this repo marks `OperatorTenancyLookup` and `shared/outbox`.

### Rule 4 · A guard may ship without its completion route — if it fails closed and the gap is stated.

Slice 1 shipped `must_change_password` on `staff_credentials` **and** the login check that honours it:

```java
if (credential.isMustChangePassword()) {
    // No token. Issuing one "so the change endpoint can be called" makes the account fully usable
    // while nominally requiring a rotation.
    throw new ApiException(IdentityErrors.PASSWORD_CHANGE_REQUIRED);   // 409, no token
}
```

No route completed the change until slice 6. That is a **dead end by design**, and consistent, because the
dead end refuses. Slice 7 repeated and tightened it: `agent_credentials.must_change_pin` ships with its check
(`PIN_CHANGE_REQUIRED`, 409, no token) and no completion route, and says why that strands nobody — *nothing
in this slice can set the flag.* That is the sharper half of the rule.

| | slice 1 · `must_change_password` | slice 7 · `must_change_pin` |
|---|---|---|
| completion route | absent until slice 6 | absent until agent provisioning |
| can anything set the flag? | **yes** — `RootBootstrap` | **no** — no surface writes it |
| therefore | ROOT was deliberately behind the door, written down | nobody is behind the door at all |

**The test.** Of every guard with no completion route: does refusing cost the caller anything unrecoverable,
and can any code path *in this commit* put a real account behind it? If the second is yes, the route ships now.

### Rule 5 · Every branch a later slice will reach is exercised, or unreachable by a type — never merely unvisited.

Slice 2 added the tenancy claim as `principal.tenancy() == null ? null : principal.tenancy().name()`. The
null branch never executed (every principal from slice 2 to 6 was staff, and every staff member has a
tenancy) and was wrong the whole time: `JwtClaimsSet.Builder` rejects a null value. **The first agent sign-in
in slice 7 was a 500** — five slices after the line was written, in a commit about agents, not tokens. The
author anticipated the future case, handled it, documented it. What they missed is **two kinds of
unreachable**:

```
   unreachable by a TYPE or CONSTRAINT               unreachable by a FACT ABOUT TODAY'S DATA
   Principal's constructor refuses an agent          "every principal has a tenancy"
   with permissions — no caller can build one        → true slice 2, false slice 7
   holds until somebody changes the type,            EXPIRES SILENTLY. Nothing fails on the commit
   which is a visible edit                           that invalidates it — it fails on first use
```

A fact about today's data is not a proof; it is a schedule. Three repairs, best first: **make the state
unconstructible** (`Principal`'s constructor); **exercise it now** (construct the future state in a test
today — it would have failed the day the line was written); or **delete the branch and fail loudly**
(`Objects.requireNonNull` beats a handler nobody has run). The actual repair was to omit the claim rather
than write null — `parse` already reads a missing tenancy claim as null. Note the asymmetry: empty
*collections* are still written (shape does not vary with contents); a scalar has no empty form, so it is
omitted.

**The test.** For every branch handling a case that cannot happen yet: what makes it impossible — a type, a
constraint, or a fact about the rows today? Only the first two are proofs. If the third, write the test now.

### Rule 6 · Reserved means empty and closed, not permissive.

Reserving space for later has exactly one safe form: `Audience.AGENT` as `Set.of()` (permits no type);
`shared/outbox`, `shared/messaging` as a `package-info.java` with **no classes** (no partial `enqueue` to
misuse); `PrincipalType` as one constant (no `UNKNOWN` placeholder to leak into a token);
`agent_credentials.must_change_pin` as a column plus a check with no writer. The forms that are reservations
in name only — `EnumSet.allOf(...)` "tighten later", `return true; /* TODO */`, `Optional.empty()` read as
"no restriction", `void reserve(cmd, Integer maxSeats)` — are each a *decision to permit* in the syntax of a
decision deferred. The last is the shape doc 21 identifies as killing the pass-through channel: whatever
`null` means today, somebody will make it mean *no limit*, and an agent with no quota row sells the whole
bus. **"Unbounded" is a decision, so the rule's owner makes it, through one greppable named constructor** —
`SeatAllocationCeiling.unbounded(decidedBy)`. *(Aspirational: `quota`, `seat-inventory`, `booking` are
skeletons; the channel and DAG edges are settled, the classes are not.)* **A `TODO` on a security decision is
a permission grant with an apology attached** — the placeholder refuses.

**The test.** Read every reserved thing as though the next slice never lands. If that reading is "open", it is
not reserved.

### Is this commit consistent?

Seven questions, five minutes, each with a wrong answer rather than a judgement call. Answer them before
pushing — the reviewer cannot see which branches you decided were unreachable.

| # | Ask | You are inconsistent if |
|---:|---|---|
| **1** | For every path this module does not implement yet — **what is the response?** | the answer is "it does not come up": a fail-open path you have not found |
| **2** | Does any new code **permit** what it does not check — a `return true`, a `TODO`, an `Optional.empty()` read as "no restriction", a nullable limit? | any exists. Make it refuse, or write the check |
| **3** | Does every name in every comment, javadoc, migration header and doc **resolve in the tree**? | one does not and is not marked future. Grep, do not remember |
| **4** | Are any new branches **unreachable today** by a *type/constraint* or only by a *fact about the data*? | it is a fact about the data and no test constructs the future state |
| **5** | Is any published type at its **final shape** even if contents are partial? | completing it later changes a consumer's call sites, and a second module already compiles against it |
| **6** | Does any guard here have **no completion route**? | something in this commit can put a real account behind it |
| **7** | Is every gap **written down** where the next person will read it? | it lives only in your head, or only in a commit message nobody greps |

Question 7 keeps the other six honest. `AgentCredential`'s javadoc names the horizontal attack per-account
lockout cannot see and says plainly it is exposed until slice 8: a stated gap is in the file the next slice
opens, it names the failure not the task, and **it does not claim to be handled.** A partial module that
answers all seven is finished for this commit; a complete one that fails any is not.

---

## The gates

A module is not done when it compiles and the suite is green. **It is done when the things that fail silently
have been checked by hand** — because the build cannot check them. The architecture rules read bytecode, so
they see an illegal import and never a native query naming another module's table; a migration folder nobody
registered is not an error to Flyway, it is silence. Each gate is cheap at its own moment and expensive one
gate later: a package renamed at Gate 1 is a `git mv`; after Gate 2 it is a migration folder, a Flyway
history table, and an edit to a file in a module you do not own.

> **Status.** `identity-access`, `shared` and `api-contracts` are the only modules with code. The other
> **24 are empty skeletons** — a pom and two `package-info.java` files each. So Gates 0 and 1 have been
> walked 27 times and Gates 2–6 exactly once. ([21](21-inter-module-communication.md) says 25 skeletons;
> `for d in modules/*/; do find $d/src/main/java -name '*.java' | wc -l; done` is what gives 24 today.)
> Checks that name a file existing only under `modules/identity-access` are marked **(one instance)**.

### Gate 0 · Specify the module, then place it

**The largest, and the only one with nothing to run.** Every other gate checks something a command can
check. This one is a document you write before any code exists — *what is this module, and where does it
sit* — and it is the one that cannot be fixed later without a rewrite, because a wrong entity model or a
wrong ownership boundary is not a bug inside your module, it is the shape sixteen others compile against.

The output of this gate is **the module's design note**: the head of its 40-series document — the "what this
module is for" and "entities and their attributes" sections that `40-identity-access.md` already carries,
written first and filled in as slices land. It is reviewed and agreed before a line of code, because the
cost of moving a column out of a module is a migration, a re-key of every handle that pointed at it, and a
coordinated change in a module you do not own — and the cost of deciding it correctly on paper is an
afternoon.

#### 0a · The specification — what you are building, and why each part exists

- [ ] **The work, in one paragraph, in the domain's own words.** What question does this module answer for
      the rest of the system? It must match the module's row in [20](20-module-catalog.md) and use the
      vocabulary of [00](00-glossary.md) — not invent synonyms. `identity-access` answers *"who is acting,
      what may they do, whose rows may they touch"*, and owns the credential lifecycle behind all three. A
      module whose one-paragraph job needs three "and also" clauses is two modules.

- [ ] **Every entity named, and paired with the real-world thing it is — and is *not*.** This is the single
      most important line in the specification, because getting it wrong is how a codebase starts lying. The
      entity is `StaffIdentity`, **not** `Staff` — the person, their contract and payroll are the `staff`
      module's aggregate; this row is only the *login*, and the two have independent lifecycles (someone can
      be employed with no login, or keep a login through a change of role). One name for two different things
      is a bug waiting for the second author.

      | Entity | Is | Is **not** (who owns that) | Lifecycle |
      |---|---|---|---|
      | `StaffIdentity` | a login | the employee (`staff`) | may outlive or precede employment |
      | `AgentIdentity` | a login | the selling agent (`agent`) | login only; grants live elsewhere |
      | `StaffCredential` | password + lockout state | — | replaceable without touching the identity |
      | `StaffOperator` | a membership | the operator (`tenancy`) | many per person, one company |

- [ ] **Every attribute, with the rationale written next to it.** Not "it seemed useful" — a sentence saying
      what breaks without it, or what it defends. **A column nobody can explain is a column nobody should
      add.** The codebase already does this in javadoc; the specification is where it is decided:

      | Attribute | Type | Why it exists / what it defends |
      |---|---|---|
      | `id` | `Long`, module-private | the primary key. **Never crosses a boundary** — see the id/uid split below |
      | `uid` | `UUID`, public | the handle every other module holds. Minted in Java at construction so it exists before flush, which is what lets `equals`/`hashCode` use it |
      | `company_uid` | `UUID`, nullable | the anchor of the cross-company guard; **null for everyone but operator staff**, and the database enforces the equivalence |
      | `status` | enum | asked through `canAuthenticate()`, never compared inline, so a fifth status cannot silently become loggable |

- [ ] **The id/uid split is stated once, for the module.** `Long id` is module-private and never leaves;
      `UUID uid` is the only handle that crosses a boundary. Every entity follows it, so it is decided here
      rather than per-table.

- [ ] **Every relationship, with its cardinality and what enforces it.** A relationship the specification
      names is a constraint the migration must carry — Gate 2 checks the constraint exists, but *this* gate
      is where you decide it must:

      | Relationship | Cardinality | Enforced by | Defeats |
      |---|---|---|---|
      | identity → credential | one ↔ at most one | `UNIQUE` on the FK | two live passwords, one carrying the lockout counter |
      | identity → memberships | one ↔ many | none needed | a shared-services agent serving two depots |
      | membership → company | many ↔ one | **composite FK within the module** | one credential reaching two companies' data |

- [ ] **Edge cases enumerated *before* code, especially what absence means.** This is where this project's
      real bugs were born. For **every nullable column and every collection**, write down what the empty or
      null case *means* — because the dangerous reading is always one line away:

      | Empty / null | Wrong reading (the bug) | Correct meaning | Decided by |
      |---|---|---|---|
      | empty operator list | "reaches all operators" (unrestricted) | "reaches none" — refuse | `OperatorScope` returns a sentinel, never an empty `IN` |
      | `company_uid IS NULL` | "any company" | "platform staff, no company" | the `CHECK` equivalence |
      | no credential row | "sign in freely" | "cannot sign in yet" (PENDING) | fail closed at the login check |

      **"Empty means all" is the single most expensive line in this project's history** — five modules in the
      reference implementation each read it the wrong way. Deciding it on paper, per field, is what stops it.

- [ ] **What it OWNS, in one sentence, matching its row in [20](20-module-catalog.md).**

- [ ] **What it must NOT own, written as absences.** Load-bearing, not filler: `documents` names no owner,
      which lets `fleet`/`tenancy`/`agent`/`staff`/`customer` all depend on it; `promotions` and `customer`
      name no sale-path module, which keeps `booking → promotions` and `booking → customer` acyclic; `quota`
      decides an allowance and never enforces one. An absence you did not write down is an edge somebody adds
      "just this once".

**Skip 0a and:** the entity model is discovered while coding, so the boundary between this module and the
one that owns the real aggregate is drawn by whoever types fastest. A column lands here that belonged in
`tenancy`; a `Staff` entity duplicates what `staff` owns; and the "empty means all" reading ships because
nobody decided what empty meant. None of it fails a test — it fails a *year later*, as the wrong number on
someone's screen.

#### 0b · Placement — where it sits in the graph

- [ ] **The module is a key in `ModuleCatalog.DAG`** —
      `architecture-tests/src/test/java/tz/co/otapp/buscore/archtests/ModuleCatalog.java`.
      `grep -n 'DAG.put("<module>"' <that file>`
- [ ] **Its edge set there is exactly the `tz.co.otapp.buscore` dependencies in `modules/<module>/pom.xml`.**
      `ModuleDependencyTest.the_poms_and_the_declared_dag_agree` compares them *both directions*: an edge in
      the pom but not the DAG is a dependency nobody decided on; an edge in the DAG but not the pom is a lie
      about a relationship the build does not have.
- [ ] **All seven files from [20](20-module-catalog.md) changed**, not five: root `<module>`, root
      `dependencyManagement`, the module pom, both `package-info.java`, `architecture-tests/pom.xml`, the DAG
      entry.
- [ ] **The architecture-tests entry keeps `<version>${project.version}</version>` verbatim.**
      `AnalysisClasspathTest`'s `DECLARED_DEPENDENCY` pattern matches that exact shape. Any other spelling and
      the module reads as *not analysed* — one every rule is silently green about, worse than having no rule.
- [ ] **Every edge is defensible in one sentence in the PR body.** "It compiled" is not a reason. Pom and DAG
      change in the same commit, with the reason.
- [ ] **You tried not to take the edge first.** ③ handle, ⑤ pass-through, ⑥ snapshot cost zero edges; ⑤/⑥
      leave no relationship after the write. The cheapest dependency is the one you did not take.
- [ ] **The wave is known and the dependencies are real.** Wave from [22](22-implementation-plan.md); then
      per dependency `find modules/<dep>/src/main/java -name '*.java' | wc -l` — **`2` means two
      package-infos**, an empty jar. Declaring `tenancy` today compiles and gives you nothing to call. Decide
      whether the slice is blocked or proceeds on ③ bare handles.
- [ ] **What it OWNS, in one sentence, matching its row in [20](20-module-catalog.md).**
- [ ] **What it must NOT own, written as absences.** Load-bearing: `documents` names no owner, which lets
      `fleet`/`tenancy`/`agent`/`staff`/`customer` all depend on it; `promotions` and `customer` name no
      sale-path module, which keeps `booking → promotions` and `booking → customer` acyclic; `quota` decides
      an allowance and never enforces one.
- [ ] **A channel chosen per neighbour, before code** — ① … ⑥ from
      [21](21-inter-module-communication.md), each with the reason the cheaper one was rejected.
- [ ] **If the name ends `-adapter`: nothing may depend on it. No test enforces this** — the property holds
      only because no module's DAG entry lists an adapter, and a single commit adding one to the pom *and* the
      DAG leaves the whole suite green. Reviewer's job.

### Gate 1 · Structure

- [ ] **Directory and package agree, computed:**
      `modules/<kebab-name>/src/main/java/tz/co/otapp/buscore/<kebabnamewithoutdashes>/`.
      `ModuleCatalog.packageRootOf` derives the package from the *module name*, and both `ModuleBoundaryTest`
      and the bytecode half of `ModuleDependencyTest` generate their patterns from it — so a package that does
      not match its directory **is policed by nothing, and the build stays green**. Verify
      `ls modules/<m>/src/main/java/tz/co/otapp/buscore/` prints exactly one name, no dashes.
- [ ] **`artifactId` equals the directory name; groupId is `tz.co.otapp.buscore` exactly.**
      `ModuleDependencyTest.INTERNAL_DEPENDENCY` spells the groupId out rather than wildcarding, so a drifted
      coordinate is an edge the test cannot see, not a warning.
- [ ] **The published root holds only ports, value objects and published enums.** If a name there is not
      something another module will import, it belongs under `internal/`. Publishing is a *move*, not an
      annotation — which is why it survives review.
- [ ] **`package-info.java` at the root and at `internal/`, and both true today.**
- [ ] **Internal sub-packages named as [10](10-module-layout.md) lists them** — `internal/api/<audience>`,
      `config`, `domain/entity`, `domain/dto`, `domain/enums`, `repository`, `security`, `service` +
      `service/command` + `service/impl`. Request/response types live in `internal/domain/dto`, **not** in
      `api-contracts`, until a *second* module needs one.
- [ ] **`internal/config/<Module>ModuleConfig.java` exists and registers the module's own beans** —
      `@ComponentScan` over this module's `internal.service` and `internal.api`, plus `@EnableJpaRepositories`
      and `@EntityScan` if it owns tables. The assembler scans `tz.co.otapp.buscore` and excludes
      `…internal.(?!config.)…`, so **a `@Service` this class does not reach is not a bean** — the first thing
      to check when an autowire fails.
- [ ] **If the module owns tables, that config carries `@Profile("!no-database")`**, as
      `IdentityAccessModuleConfig` does — otherwise `BusCoreSmokeTest`'s database-free context fails to start,
      looking like a test problem rather than a wiring one.
- [ ] **Names follow [11](11-naming.md):** no `I` prefix, no abbreviation (`TransactionPin…`, never
      `TxnPin…`), `<verb>At` for instants, `<what>Hash` for stored secrets, `<thing>Uid` for a cross-module
      reference — the suffix marks it as a handle with no foreign key.

### Gate 2 · Persistence

- [ ] **Migrations live in `modules/<m>/src/main/resources/db/migration/<pkgwithoutdashes>/`** — the
      dash-stripped name: `seat-inventory` → `seatinventory`.
- [ ] **Numbering restarts per module.** Your `V1__` does not collide with `identity-access`'s, because each
      module gets `flyway_schema_history_<module_with_underscores>`. Never renumber, never write in another
      module's folder.
- [ ] **The module is registered in `FlywayMigrationsConfig.MODULES`** —
      `services/bus-core/src/main/java/tz/co/otapp/buscore/config/FlywayMigrationsConfig.java`,
      `new ModuleMigrations("<module>", "<pkgwithoutdashes>")`, **in the same commit as the first
      migration**. *(One instance: the list has exactly one entry today.)*

> **The trap, stated exactly.** The list lives in `services/bus-core`; the migrations live in `modules/<m>`;
> **nothing but that list connects them.** Forget the entry and Flyway is never pointed at your folder — so it
> raises nothing, because it was never asked. The emptiness check that turns "found no migrations" into a
> startup failure only runs *for modules in the list*. Boot's own Flyway is off. What you see instead is
> Hibernate `ddl-auto: validate` failing on a missing table — reading as *the database is wrong* rather than
> *the list is wrong*, whose natural fix (apply the SQL by hand) makes it vanish locally and persist in every
> fresh environment forever. **And if the slice has no entity yet** — a seed-only migration, a lookup table —
> nothing fails at all, and the table is simply absent in production. The mirror mistake is loud on purpose:
> registered with the wrong folder name, the emptiness check throws at startup naming the module and the path.

- [ ] **Startup says so.** The log line is `<module>: N migration(s) applied, M known, history in
      flyway_schema_history_<module>`. No line, no migrations — read it once against a real database.
- [ ] **Versioned files are immutable once applied** (checksum). A change to an applied `V__` is a new
      migration, never an edit.
- [ ] **Every `R__` repeatable is idempotent.** Flyway re-runs it whenever its checksum changes — `ON
      CONFLICT … DO UPDATE`, and an authoritative `DELETE` before re-inserting a set, as `R__seed_rbac.sql`
      does so a permission removed from a role is actually removed.
- [ ] **You do not need `MODULES` ordering.** List order is run order, and matters only where one module's
      schema references another's — which none may. **If you need to run after somebody, you have a
      cross-module foreign key you are not allowed to have.**
- [ ] **`ddl-auto: validate` agrees with the entities**, and entity plus migration land in the same commit.
- [ ] **Timestamps are plain `timestamp` holding UTC, never `timestamptz`.**
      `preferred_instant_jdbc_type: TIMESTAMP` in `application.yml` is the single property that makes
      `Instant` validate; an entity reaching for `OffsetDateTime` breaks validation on every table, starting
      with `created_at`.
- [ ] **Every table carries `id`, `uid`, `created_at`, `updated_at` from `BaseEntity`**, and `uid` has *no*
      database default — it is minted in Java at construction so it exists before flush, which lets
      `equals`/`hashCode` use it.
- [ ] **Where a rule can be a constraint, it is one**, named per [11](11-naming.md): `ux_… / ix_… / ck_…`.
      A check in application code is repeated wherever the row is written, and the copy that is forgotten
      fails silently — it does not throw, it commits.
- [ ] **Take the constraints still available inside your own module.** `staff_operators` cannot have an FK to
      `tenancy`'s `operators`, but `fk_staff_operators_same_company` holds the pair together within
      `identity-access` — worked through in the slice walk below.
- [ ] **Enum columns persist the name (`EnumType.STRING`).** Appending a constant is free; renaming or
      reordering one is a migration.
- [ ] **Every lookup matches the index that guarantees it.** A case-sensitive query against a `lower()`
      functional index does not error — it silently finds nothing, and the user is told their credentials are
      invalid with no error explaining why.

### Gate 3 · Boundaries

- [ ] **The published surface is minimal and named for the question it answers.** No module-wide facade: a
      caller that needs who-is-acting must not compile against credential resets. `PrincipalContext` has two
      methods.
- [ ] **Nothing at the published root names a type under `internal/`:**
      `grep -rn '\.internal\.' modules/<m>/src/main/java/tz/co/otapp/buscore/<pkg>/*.java` → must print
      nothing. **No rule catches this**: `ModuleBoundaryTest` forbids classes *outside* the module from
      touching `…internal..`, and your port is inside it — so your module stays green and **the caller goes
      red**, possibly waves later, with a failure that reads as their mistake and a fix in your file. With 24
      modules having no callers, it can stay green indefinitely.
- [ ] **No entity crosses the boundary.** Publish a view record with an `of(entity)` projection. An entity
      hands the caller your `internal` types through its associations with no naming import, adds every future
      column to the wire silently — including the day it is a credential hash — and serialises a lazy
      association outside any transaction.
- [ ] **Cross-module references are bare `uuid` columns**, named `<thing>_uid`: no FK, no association, never
      joined. `grep -rn 'REFERENCES' modules/<m>/src/main/resources/db/migration/<pkg>/` — **every hit must
      name a table this module owns.** A constraint across a boundary inverts the build order (wave-2 cannot
      migrate against a wave-5 table) and welds two migration histories together.
- [ ] **No SQL names another module's table:** `grep -rn 'nativeQuery\|@Query' modules/<m>/src/main/java` and
      read every hit. **Nothing enforces this — the rules read bytecode, and a table name in a string is not
      a type reference.** A join onto `wallet_entries` from `booking` passes every check in the suite. The
      single most important review item in the whole system.
- [ ] **Every bare handle fails closed where it is resolved.** A uid that no longer resolves produces a
      refusal — never an empty result, never a skipped `WHERE`. `if (uids.isEmpty()) { /* no filter */ }`
      turns "no operators" into "all rows".
- [ ] **If you took ⑤ pass-through:** the value type belongs to the **enforcer**, not the decider; it is a
      required, total argument (never a nullable `Integer` read as *no limit*); lifting it has one greppable
      shape, `unbounded(decidedBy)`.
- [ ] **If you promoted a type to `api-contracts`:** a *second* consumer exists today, arriving in this
      commit. `api-contracts` is depended on by 26 modules — a type there turns a one-module change into a
      full-reactor rebuild.
- [ ] `mvn -pl architecture-tests -am test` green: pom↔DAG both directions, DAG acyclic, every reactor module
      in the DAG, no bytecode reference to an undeclared module, no outside class in anyone's `internal`,
      every module on the analysis classpath.

### Gate 4 · The HTTP surface

- [ ] **Every handler returns `ApiResponse<T>`**, the one envelope from [12](12-api-conventions.md) — every
      key present on success and failure alike. No second wrapper, no `204`: a void operation returns `200`
      with `data: null`.
- [ ] **Error codes are `DOMAIN.CONDITION`**, in the module's own `internal/domain/enums/<X>Errors.java`
      implementing `ErrorCode`, published at the root **only** when a caller must name them (`ScopeErrors`
      is; `IdentityErrors` is not). Distinct causes get distinct codes. **A released code is added to, never
      repurposed or renamed.**
- [ ] **Controller package and mapped prefix agree**: `internal/api/admin` → `/admin/v1/**`,
      `internal/api/agent` → `/agent/v1/**`. Mappings relative; `/api` comes once from the context path. Rows
      addressed by uid: `/uid/{uid}`.
- [ ] **Every handler is `public`:**
      `grep -rn 'ApiResponse<[^>]*> [a-z][A-Za-z]*(' --include=*.java modules/<m>/src/main/java | grep -v 'public '`
      → must print nothing. Spring's method-security proxy **does not advise a package-private method**, so a
      gated package-private handler is a silent no-op — annotation present, door open (breaks row 3).
- [ ] **Every `@PreAuthorize` concatenates a `Permissions` constant:**
      `grep -rn '@PreAuthorize(' --include=*.java modules services | grep -v 'Permissions\.'` → must print
      nothing. SpEL is not compiled, so a typo inside the quotes is a permission nobody holds and **the route
      silently refuses everyone forever**.
- [ ] **`hasAuthority(` appears nowhere in the reactor:**
      `grep -rn 'hasAuthority(' --include=*.java modules services | grep -v ' \* '` → must print nothing.
      ROOT's authority is one branch inside `PermissionGuard.holds` that a bare expression never reaches, so
      the first one merged locks the break-glass identity out of the system it exists to rescue.
- [ ] **Every new permission code is in `Permissions.ALL` *and* in `R__seed_rbac.sql`, in one commit.** Both
      files live in `identity-access`, not your module — the accepted cost of keeping the constants beside the
      seed. **A code declared but not seeded refuses everyone, forever, silently** (breaks row 8);
      `RbacIntegrationTest.catalog_agrees_in_both_directions` is the only backstop. *(Aspirational: no module
      other than `identity-access` has declared a permission, so this cross-module edit has never happened.)*
- [ ] **Both checks run on an operator-owned route** — `@perm.has(...)` answers *what*,
      `OperatorScopeResolver.require()` answers *whose*, neither substitutes for the other. A platform admin
      who reaches every operator's vehicles still needs `VEHICLE.READ` to read one.
- [ ] **List queries filter in the query, binding `scope.platform()` *and* `scope.filter()`** — never the
      list alone, never fetch-then-discard: a hundred rows filtered to three looks to the client like a total
      of three.
- [ ] **Authority is never read from a body.** An `agentUid` in a body is a claim, not a fact. Where a caller
      genuinely must name something, it is a query parameter validated against their own scope —
      `OperatorScope.requireTarget`, which can only select among operators they already reach.
- [ ] **The audience gate is exercised in the currently reachable direction.** A staff token must be refused
      on `/agent/v1/**` (`AUTH.AUDIENCE_MISMATCH`); any public route is public because it *presents its own
      credential*, never because someone forgot it.
- [ ] **Pagination lives under `meta`**, one shape, and an unknown sort property is refused rather than
      silently dropped.

### Gate 5 · Tests

**A thing that fails closed announces itself the first time anyone uses it. A thing that fails open announces
nothing, ever.** So the question is not "is it tested" — it is *would this test go red if the guard were
deleted?*

| What fails open | The test that must exist | Why the obvious test proves nothing |
|---|---|---|
| a permission declared but not seeded | compare `Permissions.ALL` with `SELECT code FROM permissions`, **both directions** | every test runs as an admin holding every *seeded* code, or as ROOT which bypasses the guard |
| a gated handler package-private, or `@EnableMethodSecurity` removed | a caller **without** the permission gets `403` | a test asserting `200` for a permitted caller passes with the guard gone |
| a ③ handle that no longer resolves | resolve a **dangling** uid, assert a refusal | ③ is nearly always tested with a valid handle |
| an empty operator scope read as "all" | assert `filter()` never empty and `permits(null) == platform()` | a scope of one operator behaves identically under both readings |
| a ⑥ snapshot silently re-synced | **change the source afterwards**, assert the artefact did not move | reading the snapshot back proves only that it was written |
| a ④ event published outside the transaction | roll the business write back, assert **no** outbox row | committing both proves nothing about the failure path |
| a ② port with no implementation in some deployment | assert the fail-closed default raises `503` | the context starts either way |
| a failure side effect rolled back with the failure | assert the counter survived the refusal (`noRollbackFor`) | the refusal itself is correct in both worlds |
| a module's migrations never registered | assert the table exists, against a real container | `validate` catches it only if the slice already has an entity |

- [ ] **Unit tests mirror the internal tree** under `modules/<m>/src/test/java/…`, for pure logic —
      `OperatorScopeTest` asserts the sentinel, the null case, and the refusals.
- [ ] **Anything needing the assembler is an integration test in `services/bus-core/src/test/java/…`**,
      `@SpringBootTest` + `@Testcontainers` against `postgres:18-alpine` — nine test classes today, eight
      against a real container. **A module jar has no security chain, no envelope advice and no migration
      runner**, so a module-local test of a gated route asserts nothing about the gate.
- [ ] **Every refusal is asserted by code *and* status**, not "not 200". The code is the contract; a client
      branches on it.
- [ ] **Tests clean up what they dirty, including what a *failing* test leaves behind.**
      `RbacIntegrationTest` un-archives roles in `@BeforeEach` so one broken test does not report as six.
- [ ] **A test that moves the clock restores it** — `Times.reset()` in teardown, unconditionally. `Times` is
      a static global clock (JPA has no injection point), so a leaked `fixedAt` fails an innocent later test in
      the same JVM under whichever ordering the runner picked.
- [ ] **Time fixtures state their zone:** `(now() AT TIME ZONE 'UTC')`, never bare `now()`. The JDBC session
      zone comes from the **JVM's** while the column holds UTC (`hibernate.jdbc.time_zone: UTC`), so half the
      offset/interval combinations are a **false green**.
- [ ] **Test classes are flat, not `@Nested`.** Surefire does not descend into nested classes under JUnit
      Platform 6, so a nested suite reports success having run nothing.
- [ ] **The database-free context still starts:** `BusCoreSmokeTest` under `@ActiveProfiles("no-database")`
      catches a module dragging a datasource requirement into the web path — it has already caught one.
- [ ] `mvn -q -pl architecture-tests -am test` and `mvn -q -pl services/bus-core -am test` both green (the
      second needs Docker).

### Gate 6 · Documentation and handover

- [ ] **A `40-<module>.md` exists, or is updated in this commit**, carrying: a status line (*slices N of M*);
      **What other modules can use today** — the published surface, type by type, and nothing unpublished; the
      doors and their audiences; the error codes with statuses; the schema table saying **what each constraint
      defeats**; configuration keys with their *absent* behaviour; and what is left.
- [ ] **A numbered "Rules a later slice must not break" section, each entry with a test.** *If you cannot name
      the test, it is not a rule yet, it is a preference.* `identity-access` has sixteen.
- [ ] **Every enforcement claim was read, not assumed.** Doc 21 once claimed a hand-written ArchUnit rule for
      adapters nobody wrote, and claimed Maven catches undeclared imports it compiles happily — both survived
      because plausible. Open the test before writing that a test exists.
- [ ] **Aspirational things are marked as such, and the note is deleted in the commit that builds them.** An
      intention written in the present tense becomes a lie the moment somebody trusts it.
- [ ] **Your own `package-info.java` is not stale.** *(Live example: the root package-info of
      `identity-access` still calls the module a "scaffolded skeleton" that "owns no entities, controllers, or
      migrations" — above eleven entities, four controllers and seven migration files, and after it became a
      dependency of `services/bus-core`. It has been wrong since slice 1.)*
- [ ] **[20](20-module-catalog.md)'s catalog row still true**, and if the DAG changed,
      [22](22-implementation-plan.md)'s wave table regenerated with `python tools/waves.py` — **never
      hand-edited**. A build order maintained separately from the DAG is confidently wrong the first time an
      edge lands.
- [ ] **`bash tools/check-links.sh` green** in `bus-core-docs`, and the README index carries a row for the new
      document. A document may only link to a lower-numbered one; the ordering *is* the proof that no fact has
      two homes.
- [ ] **`services/bus-core/pom.xml` gains the `<dependency>` — the last step of the slice, never the first.**
      A module joins the deployable when it has something to serve.
- [ ] **The PR body states three things**: which edges were added and that both files changed; which channel
      was chosen per neighbour and why not the cheaper one; and which checks rest on review alone for this
      slice.

The consequence of skipping any gate is the ranked catalogue in *What each skipped check actually breaks*
below.

---

## A slice, walked through the gates

*`identity-access` **slice 5** — operator memberships, `OperatorScope`, the resolver and the cross-company
guard — is the only slice in the reactor that has passed every gate end to end. It is small (one table, three
published types, three routes) and still crosses a module boundary with no edge, puts an invariant in the
schema rather than a service, and unblocked the other 16 modules: `OperatorScope` was the gate, not slice 12.
Everything quoted is in `bus-core-api` today.*

**Gate 0a — the specification.** Written before the migration. **The work:** *"turn the authenticated
principal into the set of operators they may reach."* One entity, `StaffOperator` — and it is a *membership*,
not an operator; the operator itself is `tenancy`'s. Its attributes and their rationale: `staff_identity_id`
(whose membership), `operator_uid` (a **③ handle**, resolved against nothing), and `company_uid` — the one
that looks redundant and is not, because it is what the composite FK compares against. **The edge case that
was the whole design:** what does an *empty* membership set mean? Written down as "reaches none, refuse" —
never "reaches all" — before a line of `OperatorScope` existed, which is why that class returns a sentinel
rather than an empty list. Getting this paragraph right on paper is what made the rest mechanical.

**Gate 0b — ownership, edges, channel.** The obvious home is `tenancy`, and it is **wrong for two reasons**:
the scope is a *derivation from the authenticated principal*, and **the module that owns the input owns the
derivation**; and on the DAG `identity-access` is wave 2, `tenancy` wave 5, so routing it through `tenancy`
would push `network`, `promotions` and `customer` three waves later for a `WHERE` clause. What the module
deliberately does **not** own: it never learns what an operator *is* — `operator_uid` is a handle it stores
and never resolves. The pom gained **nothing** — the wanted edge `identity-access → tenancy` is a cycle
(`tenancy → identity-access` exists), so doc 21's answer is an inbound port, ②.

> **Not built, marked as such.** `OperatorTenancyLookup` is named in [11](11-naming.md) and doc 21 and exists
> in no source file; channel ② has **zero instances**. The honest consequence:
> `GET /admin/v1/staff/uid/{uid}/operators` returns `ApiResponse<List<UUID>>` — bare uids, no names. **The
> slice shipped the shape it could defend instead of the shape that looked finished.**

Two columns on `staff_operators` are **③ bare handles** (no FK): an FK would require `tenancy`'s tables to
exist before `identity-access` can migrate (inverting the build order) and weld two migration histories
together. Cost accepted: **nothing detects a stale handle**, so every resolution fails closed — checked at
Gate 3.

**Gate 1 — structure.** Three files move to the package root; ~70 stay under `internal/`:

```
identityaccess/                      ← published
  OperatorScope.java                 the value: platform(), filter(), permits(), requireTarget()
  OperatorScopeResolver.java         the derivation: Principal -> OperatorScope
  ScopeErrors.java                   the refusals: SCOPE.NOT_AUTHORISED, SCOPE.OPERATOR_REQUIRED
  internal/ … StaffOperator, StaffOperatorRepository, StaffAdministrationServiceImpl,
              StaffAdminController, IdentityErrors (AUTH.* — stays hidden, the contrast)
```

`OperatorScopeResolver` is a concrete `@Component` **with no interface** — the interface/impl split is for a
port somebody may substitute, and this is fifteen lines of branching over a `Principal`.

**Gate 2 — schema: where a rule can be a constraint, it is one.** `V4__create_staff_operators.sql` adds one
table and four constraints, only one of which is the feature:

| Constraint | Defeats |
|---|---|
| `ck_staff_identities_company_matches_tenancy` — `CHECK ((tenancy = 'OPERATOR') = (company_uid IS NOT NULL))` | operator staff with no company, and platform staff with one. An **equivalence** so neither half satisfies alone |
| `ux_staff_identities_id_company UNIQUE (id, company_uid)` | nothing on its own — `id` is already the PK. It exists **only** so the pair can be referenced |
| `fk_staff_operators_same_company FOREIGN KEY (staff_identity_id, company_uid) REFERENCES staff_identities (id, company_uid)` | **one credential reaching two companies' data** |
| `ux_staff_operators_pair UNIQUE (staff_identity_id, operator_uid)` | unlinking removing one of two rows, leaving access the caller was told they lost |

```
  jane  → staff_identities (id=7, company_uid=A)          admin → staff_identities (id=9, company_uid=NULL)
      INSERT staff_operators (7, A, op=…)   ✓                  INSERT staff_operators (9, anything, …)  ✗
      INSERT staff_operators (7, A, op=…)   ✓ two depots       nothing matches NULL
      INSERT staff_operators (7, B, op=…)   ✗ no (7,B)
```

A check in `linkOperator` looks better on every axis a reviewer sees but is only *insufficient*, not *wrong*
(the "done badly" section walks that failure); the constraint buys the writer who is *not* `linkOperator` — a
bulk import, a `psql` fix, a self-service screen next year. It is possible because `company_uid` is
**duplicated onto the membership row on purpose** (without it there is no pair to constrain), and
`StaffOperator.of(staffIdentity, operatorUid)` takes the company **from the person**, not a parameter. The
service keeps a *different* check — `scope.permits(operatorUid)`, which depends on the acting principal and so
*cannot* be a constraint.

**Gate 3 — boundaries: what had to be published, and what empty means.** `OperatorScope.requireTarget`
throws `new ApiException(ScopeErrors.NOT_AUTHORISED, …)`; `OperatorScope` is published, and **a published
type may not reference an internal one**, so `ScopeErrors` went up with it (`IdentityErrors` stayed internal
— nothing published names it). The failure prevented is not a compile error here:

```
  ScopeErrors internal, referenced by OperatorScope (published) → ModuleBoundaryTest: GREEN
      the reference is INSIDE the module; the rule only fires on classes OUTSIDE it
  fleet wants SCOPE.NOT_AUTHORISED vs COMMON.FORBIDDEN
      ├── import the internal enum   ✗ ModuleBoundaryTest fails — the good outcome
      └── compare a string literal   ✓ compiles, ships, and is the actual defect
```

The second branch is what people do under deadline — the same defect `Permissions` prevents. **It is a gate
item because it can only be a gate item.** (`Principal.operatorUids` was already published in slice 1;
publishing the list *without* the derivation is the counter-example below.) Then **absence**, the reading
this slice exists to settle, because the wrong answer is one line from unrestricted access:

```
                    principal.operatorUids() == []
          ROOT / ADMIN                         OPERATOR, no memberships
          no tenancy → reaches EVERY operator   serves nobody → reaches NOTHING
          platform() == true                    refused at the resolver
```

**Both have an empty list, so the list can never be the decision — the boolean is.** Three places make the
restrictive reading structural: the resolver reads `tenancy` *before* the uid list, so ROOT/ADMIN return
`allOperators()` at the top of the switch and never reach the emptiness branch (which lets emptiness be
restrictive *everywhere else*); `filter()` returns `List.of(MATCHES_NOTHING)`, the nil uuid, never an empty
collection — removing the pressure that produces `if (uids.isEmpty()) skip the WHERE`; and the resolver
refuses `SCOPE.NOT_AUTHORISED` rather than returning `restrictedTo(List.of())`. `PARTNER` is refused both
ways, and `permits(null)` answers `platform()`. Same defect shape as ⑤'s `Integer maxSeats` in doc 21: **an
absent rule read as unrestricted rather than as a refusal.**

**Gate 4 — the HTTP surface.** `GET/POST/DELETE …/operators` gated `STAFF.READ` / `STAFF.OPERATOR_LINK` /
`STAFF.OPERATOR_UNLINK` (link and unlink are **separate codes, by the widen/narrow rule**). Two refusals that
read backwards and are right: `SCOPE.OPERATOR_REQUIRED` is **400, not 403** (platform staff must name a target
`?operator=` — validated by `requireTarget` against their own scope — because their owner is undetermined,
not forbidden); `AUTH.STAFF_NOT_FOUND` is **404, not 403** for an account in another company, so probing
cannot turn 403s into a directory of another business's staff.

**Gate 5 — tests at the layer that owns the rule.** `StaffOperatorIntegrationTest` (`@SpringBootTest` +
Testcontainers) writes raw SQL through a `JdbcTemplate`, so **nothing goes through the application** — testing
through `linkOperator` would prove only that `linkOperator` checks, and the whole reason the rule is in the
schema is the caller that forgets:

```java
long staffId = insertStaff("jane", "OPERATOR", COMPANY_A);
assertThatThrownBy(() -> insertMembership(staffId, UUID.randomUUID(), COMPANY_B))
        .isInstanceOf(DataAccessException.class);
```

**Gate 6 — the handover.** A no-op except the docs: pom, `MODULES` and DAG unchanged (the module joined at
slice 1, V4 is picked up by folder, Gate 0 added no edge). The deliverable was four edits to
`40-identity-access.md`, the one that matters being **rule 11: *an empty operator list is restrictive,
always.*** The composite FK defends itself; the `filter()` sentinel does not — it is three characters from
deletion by somebody who "obviously" should return an empty list, and rule 11 is all that stands between that
commit and a green build.

---

## The same slice, done badly

The same feature, built by competent people who never asked the questions. **Neither defect is invented** —
both are recorded against the reference implementation.

> **This code does not exist in this repo.** It is a reconstruction; the five consuming modules named are
> skeletons here, and `OperatorScope` has no consumer today.

**Defect 1 · The scope that was never published — Gates 3 and 5.** `Principal.operatorUids` is public, so
nobody decided anything. Five modules each wrote:

```java
// fleet — and four more, in scheduling, network, promotions, customer
List<UUID> uids = principal.operatorUids();
if (uids.isEmpty())    throw new AccessDeniedException("no operator");  // ← the 403 an admin gets
if (uids.size() > 1)   throw new IllegalStateException("multiple operators not supported");
return vehicles.findAllByOperatorUid(uids.getFirst());
```

Each author believed they were failing closed. But a platform scope and a broken scope have the same empty
list, so **a platform administrator holding every code in `Permissions.ALL` is refused 403 on every
operator-owned route** — no grant fixes a refusal that never consulted one, and because it is
permission-shaped the investigation goes to the wrong module. Meanwhile the fifth module, which read emptiness
correctly, serves that same admin every row — so **the answer to "may this person see this?" depends on which
module you ask.** (The `size() > 1` half cannot represent a two-depot employee, forcing two accounts.) **A
question asked in five modules gets five answers, four wrong in the same direction** — Gate 3 is answerable
once, in one place, only because it also published the derivation.

**Defect 2 · The guard that lived in a service — Gates 2 and 5.**

```java
if (!target.getCompanyUid().equals(companyOf(operatorUid)))
    throw new ApiException(ScopeErrors.NOT_AUTHORISED, "That operator is in another company.");
memberships.save(new StaffOperator(target, operatorUid));
```

It *works* — no request through this method produces a cross-company membership. It costs nothing until the
second writer, six months later: a bulk import, a `psql` fix at 02:00, a self-service screen. Each writes the
row; none read this method. **The one that forgets does not throw — it commits.** No symptom on the day: the
row surfaces when that person signs in, receives a `Principal` carrying two companies' operators, and every
scope filter correctly returns rows from both. **One credential, two unrelated businesses, no exploit
required.** Gate 2 asks *can this be a constraint?* — here yes, at one duplicated column. Gate 5's
badly-built test is the tell: it goes through `linkOperator`, passes, and **would still pass with the
constraint absent and three other writers inserting whatever they liked.**

| Gate skipped | The build reported | What was actually true |
|---|---|---|
| 3 · published surface | **green** — five private helpers, no boundary crossed | one question had five answers |
| 3 · absence | **green** — every module tested a single-operator caller | the widest caller was refused everywhere |
| 2 · schema | **green** — `linkOperator` has a passing test | the rule held for one writer out of four |
| 5 · tests | **green** — the refusal path was covered, through the service | nothing tested the writer that forgets |

**Every row is a green build.** Nothing in `ModuleDependencyTest`, `ModuleBoundaryTest` or
`AnalysisClasspathTest` fires. The suite tests what somebody thought of. **The checklist is the list of things
people do not think of** — which is why it is questions asked before the code, not assertions written after.
The badly-built version is *more* code.

---

## What each skipped check actually breaks

The item skipped under deadline is whichever looks least like today's problem, so the failures are ordered
here by the only property that decides what skipping one costs: **how long the failure stays hidden after the
commit that causes it.** Most do not *fail* — the module compiles, boots, serves traffic and passes its own
tests, then miscommunicates with a module that lands two months later. **The commit that causes the failure
and the commit that reveals it are not the same commit, not the same person, usually not the same module.**

```
                                         ▼ the commit that causes it
  ───────────────────────────────────────┬───────────────────────────────────────►  time
  15  pom ↔ DAG disagree, DAG cycle       ├─ seconds ── the build names the module
  14  deployable pom drags a requirement  ├─ seconds ── the context refuses to start
  13  bare now() in a fixture             ├───────── some machines, not others
  12  a test leaks a fixed clock          ├───────── some test orderings, not others
  11  Flyway's four traps                 ├──────────────── one environment, or one deploy
  10  migration not in MODULES            ├──────────────── first boot that owns the table
   9  a @Configuration gated off          ├──────────────── one profile, at boot
   8  permission declared, never seeded   ├─────────────────────────── first real caller
   7  @PreAuthorize written as a literal  ├─────────────────────────── first real caller
   6  pom + DAG edited together, unargued ├─────────────────────────── the rebuild fan-out
   5  native query across a boundary      ├─────────────────────────── the other module's next migration
   4  hasAuthority() instead of @perm     ├───────────────────────────────────── the incident
   3  package-private gated handler       │
   2  @EnableMethodSecurity absent        ├────────────────────────────────────────────► never
   1  module absent from analysis cp      │        (only an audit, a breach, or a hand-read)
```

Rows 1–3 have no arrival time. They are not slow failures; they are **the absence of a failure that should
have happened**, so no amount of green build is evidence against them. Row 1 is the nastiest: it does not
break a module, it breaks **the thing that would have told you a module was broken** — a module off the
analysis classpath is analysed over **zero classes, reporting green**. `AnalysisClasspathTest` catches it
(Gate 0), and its own failure mode is **red, not green** by design; its javadoc names the subtler variant, a
module visible only *transitively*, which loses its coverage the day that edge is dropped in an unrelated
refactor.

Where the enforcement actually is: **only rows 1, 8 and 15 are fully caught by the build** —
`AnalysisClasspathTest`, `RbacIntegrationTest` (needs Docker), and `ModuleDependencyTest`'s three rules. Four
are *partly* caught: row 6 (`ModuleDependencyTest` checks the edges match, never that they were justified),
row 10 (`ddl-auto: validate`, only with an entity), row 11 (the emptiness check covers the classloader trap,
not baseline or ordering), row 14 (`BusCoreSmokeTest`, narrowed to the web layer). **The other eight — 2, 3,
4, 5, 7, 9, 12, 13 — have no automated backstop at all**, the whole argument for reading the checklist rather
than trusting a green build.

Rows 4, 7 and 8 produce the *same* 403 for somebody who should pass, from three different mistakes — and two
are not in the database at all, so an investigation that starts (naturally) at the grants stays there until
somebody opens the controller:

| Cause | Where it lives | Who it refuses | Caught by |
|---|---|---|---|
| literal string in the SpEL, typo | the annotation | everyone except ROOT | nothing |
| constant declared, never seeded | `Permissions.ALL` vs the seed | everyone except ROOT | `RbacIntegrationTest`, both directions |
| `hasAuthority(...)` in place of `@perm.has(...)` | the annotation | only ROOT | nothing |
| a genuinely missing grant | `role_permissions` | one role | the feature's own test |

Rows 11–13 are intermittent for three unrelated reasons — bean instantiation order, test execution order, the
JVM's default zone — none varying with load, input or data, all going away on a retry, which is precisely why
each survives to production. And **when a guard is narrowed, its failures move to a slower row**:
`BusCoreSmokeTest` once asserted the whole app boots with nothing running (catching row 14); persistence
arrived with `identity-access`, so it was narrowed to the web layer, and the same mistake now surfaces as row
10 or 11 rather than at boot.

**If you are going to skip one, skip a fast one.** Rows 14 and 15 fail in the same commit, with the module
named. Rows 1–8 fail in somebody else's commit, weeks later, in a module that did nothing wrong. **The gates
worth defending are the ones with no failure attached** — a gate whose failure is loud is already doing its
own arguing.

---

## The one-page version

Paste into the PR description. Strike what does not apply; do not delete it.

```
Module: <m>    Slice: <n> of <m>    Wave: <w>    New pom edges: <none | list>
```

**Gate 0a · specification** *(written before code, is the head of the 40-doc)*

- [ ] the work in one paragraph, in the domain's words, matching the [20](20-module-catalog.md) row
- [ ] every entity paired with what it *is* and *is not* — which module owns the real aggregate
- [ ] every attribute has a one-line rationale; a column nobody can explain is deleted
- [ ] the `Long id` / `UUID uid` split stated; only `uid` crosses a boundary
- [ ] every relationship: cardinality + what enforces it (a `UNIQUE`, a composite FK, or nothing)
- [ ] every nullable column and every collection: what does empty/null *mean*? never "empty means all"
- [ ] what it owns / what it must NOT own, written as absences

**Gate 0b · placement**

- [ ] `grep -n 'DAG.put("<m>"' architecture-tests/src/test/java/tz/co/otapp/buscore/archtests/ModuleCatalog.java`
- [ ] DAG edge set == pom's `tz.co.otapp.buscore` dependencies, both directions
- [ ] all seven files changed: root `<module>`, root `dependencyManagement`, module pom, both `package-info.java`, `architecture-tests/pom.xml`, DAG entry
- [ ] `architecture-tests/pom.xml` entry keeps `<version>${project.version}</version>` verbatim
- [ ] every edge defended in one sentence below; the cheaper channel (③ ⑤ ⑥) tried first
- [ ] `find modules/<dep>/src/main/java -name '*.java' | wc -l` > 2 for every dependency I call
- [ ] a channel (① … ⑥) chosen per neighbour, cheaper one rejected with a reason
- [ ] nothing depends on an `-adapter` module *(reviewer's job — no test)*

**Gate 1 · structure**

- [ ] `ls modules/<m>/src/main/java/tz/co/otapp/buscore/` prints one name, no dashes
- [ ] `artifactId` == directory name; groupId `tz.co.otapp.buscore` exactly
- [ ] published root holds only ports, value objects, published enums; both `package-info.java` true today
- [ ] `internal/config/<M>ModuleConfig.java` reaches every `@Service`/`@RestController` in this module
- [ ] owns tables ⇒ that config carries `@Profile("!no-database")`
- [ ] names per 11: no `I` prefix, no abbreviation, `<verb>At`, `<what>Hash`, `<thing>Uid`

**Gate 2 · persistence**

- [ ] migrations in `db/migration/<pkg>/`, numbering restarts at `V1__`
- [ ] `new ModuleMigrations("<m>", "<pkg>")` in `FlywayMigrationsConfig` — **same commit as the first migration**
- [ ] startup log line seen against a real database; applied `V__` untouched; every `R__` idempotent
- [ ] `ddl-auto: validate` green; entity + migration in one commit
- [ ] `timestamp` not `timestamptz`; `BaseEntity` columns present; `uid` has no database default
- [ ] every rule that can be a constraint is one, named `ux_… / ix_… / ck_…`; `EnumType.STRING`; every lookup matches its index

**Gate 3 · boundaries** — the first two must print nothing

- [ ] `grep -rn '\.internal\.' modules/<m>/src/main/java/tz/co/otapp/buscore/<pkg>/*.java`
- [ ] `grep -rn 'nativeQuery\|@Query' modules/<m>/src/main/java` — read every hit
- [ ] `grep -rn 'REFERENCES' modules/<m>/src/main/resources/db/migration/<pkg>/` — own tables only
- [ ] no entity crosses the boundary; a view record with `of(entity)` instead
- [ ] every bare handle fails closed where it is resolved; empty never means "all"
- [ ] ⑤ value type owned by the enforcer, required and total; `api-contracts` promotion only with a second consumer this commit
- [ ] `mvn -q -pl architecture-tests -am test`

**Gate 4 · HTTP surface** — all three must print nothing

- [ ] `grep -rn '@PreAuthorize(' --include=*.java modules services | grep -v 'Permissions\.'`
- [ ] `grep -rn 'hasAuthority(' --include=*.java modules services | grep -v ' \* '`
- [ ] `grep -rn 'ApiResponse<[^>]*> [a-z][A-Za-z]*(' --include=*.java modules/<m>/src/main/java | grep -v 'public '`
- [ ] every handler returns `ApiResponse<T>`; no `204`; error codes `DOMAIN.CONDITION`, distinct causes distinct codes
- [ ] controller package ↔ mapped prefix agree; rows addressed by `/uid/{uid}`
- [ ] every new permission in `Permissions.ALL` **and** `R__seed_rbac.sql`, one commit
- [ ] permission **and** scope both checked; list queries bind `scope.platform()` **and** `scope.filter()`
- [ ] no authority from a body; caller-named targets validated against their own scope
- [ ] audience refusal asserted; pagination under `meta`; unknown sort refused

**Gate 5 · tests** — would each go red if the guard were deleted?

- [ ] a caller **without** the permission gets 403; a **dangling** ③ handle produces a refusal
- [ ] `filter()` never empty; `permits(null) == platform()`
- [ ] ⑥: change the source afterwards, assert the artefact did not move; ④: roll the write back, assert no outbox row; ② absent ⇒ 503
- [ ] refusals asserted by **code and status**; fixtures clean up after a *failing* test
- [ ] `Times.reset()` in teardown; `(now() AT TIME ZONE 'UTC')`, never bare `now()`; test classes flat, not `@Nested`
- [ ] `mvn -q -pl architecture-tests -am test` && `mvn -q -pl services/bus-core -am test`

**Gate 6 · handover**

- [ ] `40-<m>.md` written/updated: status line, published surface, doors, error codes, schema table saying what each constraint defeats, config keys with absent behaviour, what is left
- [ ] numbered "Rules a later slice must not break", each with a named test
- [ ] every enforcement claim opened and read; aspirational things marked; own `package-info.java` not stale; 20's catalog row still true
- [ ] DAG changed ⇒ `python tools/waves.py`, pasted over 22's table, never hand-edited
- [ ] `bash tools/check-links.sh` green; README index row present; `services/bus-core/pom.xml` dependency added last

**Consistency, before pushing**

- [ ] every unimplemented path has a named response — none is "it does not come up"
- [ ] nothing permits what it does not check: no `return true`, no security `TODO`, no nullable limit
- [ ] every name in every comment, javadoc, migration header and doc resolves in the tree
- [ ] every unreachable branch is unreachable by a **type or constraint**, not by today's data
- [ ] published shapes final; completing them later touches `switch` statements, not call sites
- [ ] no guard whose completion route is in a later slice can have a real account put behind it now
- [ ] every gap written down where the next person will read it
