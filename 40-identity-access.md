# 40 · identity-access

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[11-naming.md](11-naming.md), [12-api-conventions.md](12-api-conventions.md),
[21-inter-module-communication.md](21-inter-module-communication.md).*

**This describes code that exists**, unlike the 30-series study of a different codebase. It is updated
as each slice lands.

**Status: slices 1-5 of 12 complete.** Staff can sign in, routes are gated on permissions and on
audience, every authentication decision is recorded, and the other 16 modules are unblocked.

---

## What the module is for

It answers three questions for the whole system — *who is acting*, *what may they do*, *whose rows may
they touch* — and owns the credential lifecycle behind all three.

It does **not** own the people. A staff member's employment belongs to the `staff` module; an agent's
selling authority to `agent`; a passenger's identity to `customer`. This module owns only the *login*, and
the two have independent lifecycles — which is why the types are `StaffIdentity` and `AgentIdentity`
rather than `Staff` and `Agent`.

## What other modules can use today

| Type | Signature | Use it to |
|---|---|---|
| `Principal` | `record(uid, type, tenancy, operatorUids, permissions)` | know who is acting |
| `PrincipalType` | `STAFF` | branch on the kind of actor |
| `PrincipalContext` | `Principal require()` · `Optional<Principal> current()` | obtain the acting principal |
| `StaffTenancy` | `ROOT · ADMIN · OPERATOR · PARTNER` | know which organisation they belong to |
| `Permissions` | `DOMAIN.ACTION` constants | name a permission on a route |
| `PermissionGuard` | the bean `@perm` | gate a route |
| `OperatorScopeResolver` | `OperatorScope require()` | turn the actor into the operators they reach |
| `OperatorScope` | `platform()` · `filter()` · `permits(uid)` · `requireTarget(uid)` | limit a query or a row |
| `ScopeErrors` | `SCOPE.NOT_AUTHORISED` · `SCOPE.OPERATOR_REQUIRED` | the refusals scope raises |

```java
// who is acting
Principal actor = principalContext.require();   // throws 401 if unauthenticated

// gate a route - concatenate the constant, never write the literal
@PreAuthorize("@perm.has('" + Permissions.ROLE_GRANT + "')")
public ApiResponse<Void> grant(...) { ... }

// limit a query to the operators this caller reaches
OperatorScope scope = scopes.require();
return vehicles.findAllInScope(scope.platform(), scope.filter());
```

```java
// the repository side: bind the boolean AND the list, never the list alone
@Query("select v from Vehicle v where (:platform = true or v.operatorUid in :operatorUids)")
List<Vehicle> findAllInScope(@Param("platform") boolean platform,
                             @Param("operatorUids") Collection<UUID> operatorUids);
```

### Empty never means "all"

This is the one thing to get right when consuming `OperatorScope`, because the wrong reading is one line
away and it is unrestricted access:

```java
if (uids.isEmpty()) { /* skip the WHERE clause */ }   // turns "no operators" into "every row"
```

A platform scope and a broken scope **both** have an empty uid list, so code keying off emptiness gets it
exactly backwards — the caller with the widest reach looks identical to the caller with none. So:

- `filter()` never returns an empty collection. It returns a sentinel (the nil uuid) that matches nothing,
  which is safe because the `:platform = true` disjunct has already opened the query by then. It also means
  the `IN` bind never fails, which an empty list would.
- The resolver **refuses** operator staff with no memberships rather than handing back an empty scope, so
  the mistake cannot be made downstream either.
- `permits(null)` answers `platform()`. A row owned by no operator is reachable only by platform staff.

In the reference implementation five modules each grew their own version of this, and **four refused an
empty uid list** — so a platform administrator holding every permission in the system was refused 403 on
every operator-owned endpoint. All five also refused a list of longer than one, so nobody could serve two
operators. One resolver means one answer.

### Naming the operator on a create

A scope cannot say which operator a *new* row belongs to. That one question is answered by the
`?operator=` **query parameter**, validated by `requireTarget` against the caller's own scope — so it
selects among operators they already reach and can never widen them. It is not in the body, because
authority never is.

Platform staff always have to supply it. That reads backwards and is not: they reach every operator, so
the owner is genuinely undetermined. `SCOPE.OPERATOR_REQUIRED` is **400**, not 403 — nothing is refused,
the request is incomplete.

`Principal` carries no `Long` id, and never will: the numeric key does not cross a module boundary.

**The permissions on it are a snapshot.** They are resolved at sign-in and carried in the token, so a role
revoked one minute later stays effective until the token expires. That is the trade for not querying the
database on every request, and it is why the lifetime is short. Where a change must take effect
immediately the lever is session revocation — a later slice — not revoking the role.

## The doors

| Method | Path | Gate | Returns |
|---|---|---|---|
| `POST` | `/api/admin/v1/auth/login` | public | token, expiry, display name |
| `GET` | `/api/admin/v1/auth/me` | bearer | the signed-in account |
| `GET` | `/api/admin/v1/roles` | `ROLE.READ` | the role catalog |
| `GET` | `/api/admin/v1/permissions` | `PERMISSION.READ` | the permission catalog |
| `POST` | `/api/admin/v1/staff/uid/{uid}/roles` | `ROLE.GRANT` | — |
| `DELETE` | `/api/admin/v1/staff/uid/{uid}/roles/{code}` | `ROLE.REVOKE` | — |
| `POST` | `/api/admin/v1/staff` | `STAFF.CREATE` | the created account, **201** |
| `GET` | `/api/admin/v1/staff` | `STAFF.READ` | the accounts the caller administers |
| `GET` | `/api/admin/v1/staff/uid/{uid}` | `STAFF.READ` | one account |
| `GET` | `/api/admin/v1/staff/uid/{uid}/operators` | `STAFF.READ` | its operator memberships |
| `POST` | `/api/admin/v1/staff/uid/{uid}/suspension` | `STAFF.SUSPEND` | — |
| `DELETE` | `/api/admin/v1/staff/uid/{uid}/suspension` | `STAFF.RESTORE` | — |
| `POST` | `/api/admin/v1/staff/uid/{uid}/operators/{operatorUid}` | `STAFF.OPERATOR_LINK` | — |
| `DELETE` | `/api/admin/v1/staff/uid/{uid}/operators/{operatorUid}` | `STAFF.OPERATOR_UNLINK` | — |

A withdrawal is modelled as a **suspension resource** — `POST` to create, `DELETE` to remove — rather than
a status field a caller may set to anything. That is what lets the two directions carry separate
permissions, which is the whole point of splitting them: during an incident the people who should be able
to cut an account off are not always the people who should be able to turn it back on. `ACTIVE` is
therefore not an accepted value on the `POST`; reaching it is a `DELETE`.

**The subject is always in the path, never in the body.** A body naming both parties makes it possible for
the two to disagree.

### The audience gate

Every route sits behind one of two audiences — `/admin/**` for staff, `/agent/**` for agents — decided at
the door from the token's `aud` claim, before any permission is evaluated. It appears to do nothing today
because there is only one audience, which is exactly why it landed in slice 3 rather than being
retrofitted once a staff token could be replayed against an agent route.

`AUTH.AUDIENCE_MISMATCH` is **not** a missing grant, and no role fixes it. Three gates, three remedies:

| Code | Means | What the caller does |
|---|---|---|
| `AUTH.AUDIENCE_MISMATCH` | wrong kind of caller | nothing — no grant fixes it |
| `COMMON.FORBIDDEN` | lacks the permission | ask for the role that carries it |
| `SCOPE.NOT_AUTHORISED` | another operator's rows | nothing — the row is not theirs |

### What a permission cannot say

`@PreAuthorize` asks only whether a caller holds a code. It cannot express *"may create an account, but
not one more powerful than their own"*, because that depends on the **target** as well as the actor. Those
limits live in the service, and each one **fails open** when missing — the caller does hold the code, and
the route does let them through:

- Nobody creates `ROOT`, and nobody suspends it. The break-glass identity is what rescues the system when
  administration itself is broken.
- An operator administrator creates only `OPERATOR` accounts, only in their own company. **The body does
  not get a say** — a body that chose the company would be an authority field.
- Linking an operator requires the *linker* to reach it already, so a membership cannot hand out access the
  linker does not have.
- An administrator cannot withdraw their own access: undoing it needs a session they would no longer have.

New accounts are created `PENDING` **with no credential row**, so whoever provisions accounts never learns
the password of the accounts they provision. Setting that password is slice 6.

### Two boundaries, and confusing them is the bug

| Bounds | By | Used by |
|---|---|---|
| **Administration** — whose accounts you manage | company | the staff admin surface |
| **Data** — whose vehicles, trips, bookings you see | operator memberships | every other module |

Scoping administration by memberships instead would strand every newly created account: it has none, so it
would be invisible to the administrator who just created it.

Another company's account answers **404, not 403** — the one deliberately vague refusal on this surface.
Everywhere else the caller has already been granted administrative permission and precision discloses
nothing; here 403 would confirm that a uid names a real account in a company they cannot see, and repeated
probing turns the difference into a directory of another business's staff.

Grant and revoke are both **idempotent**: granting a role already held, or revoking one not held, succeeds
and changes nothing. A retried request must not be an error a caller can do nothing about, and during an
incident an error for "they already did not have it" is noise at the worst moment.

Public means *presents its own credential*. Everything else is `authenticated()` by default, so a route
added tomorrow is protected by omission rather than by someone remembering.

### Error codes

| Code | Status | Meaning |
|---|---|---|
| `AUTH.INVALID_CREDENTIALS` | 401 | **Unknown identifier, wrong password, or any non-active account** |
| `AUTH.ACCOUNT_LOCKED` | 423 | Too many consecutive failures |
| `AUTH.PASSWORD_CHANGE_REQUIRED` | 409 | Correct password, but it must be rotated. **No token issued** |
| `AUTH.NOT_AUTHENTICATED` | 401 | No usable token on a protected route |
| `AUTH.STAFF_NOT_FOUND` | 404 | No such staff account |
| `AUTH.ROLE_NOT_FOUND` | 404 | No such role code |
| `AUTH.ROLE_NOT_GRANTABLE` | 409 | The role is archived, or is for a different class of staff |
| `AUTH.STAFF_ALREADY_EXISTS` | 409 | The username or email is taken |
| `AUTH.STAFF_NOT_MUTABLE` | 409 | ROOT, or the caller's own account |
| `AUTH.TENANCY_NOT_PERMITTED` | 403 | The caller may not administer an account of that kind |
| `AUTH.COMPANY_REQUIRED` | 400 | An operator account was requested without a company |
| `AUTH.AUDIENCE_MISMATCH` | 403 | Right credential, wrong surface |
| `SCOPE.NOT_AUTHORISED` | 403 | Outside the caller's operator scope |
| `SCOPE.OPERATOR_REQUIRED` | 400 | A create needs an owner and the scope names no single operator |
| `COMMON.FORBIDDEN` | 403 | Authenticated, but lacks the permission |

The administration codes are freely distinguishable, unlike the sign-in ones: the caller has proved who
they are and holds the permission to administer accounts, so a precise message discloses nothing they
could not discover through the surface they already hold.

**One code covering three causes is the point, not laziness.** If an unknown username and a wrong
password answered differently, the sign-in endpoint would be a free tool for discovering which accounts
exist. The refusal is identical, and the code even spends the hashing time on an identifier that does not
exist so the *timing* does not distinguish them either.

`ACCOUNT_LOCKED` is the one deliberate exception. It leaks existence — five failures against a guessed
username reveals the account is real — and is accepted because these are internal staff usernames, and an
employee told only "credentials not valid" retries, deepens the lock, and calls support. **If this surface
ever serves public self-registration, revisit that first.**

## The schema

Eight tables, and the constraints are the interesting part. **Where a rule can be a constraint, it is one**
— a check in application code has to be repeated wherever the row is written, and the one that is forgotten
fails silently.

| Constraint | Defeats |
|---|---|
| `UNIQUE (tenancy) WHERE tenancy = 'ROOT'` | Two concurrent bootstraps both seeing "no ROOT" and both inserting. A service check cannot prevent it — both transactions see the same empty table |
| `UNIQUE (lower(username))`, same for email | `Alice` and `alice` as two accounts, while display casing survives |
| `UNIQUE` on the credential's foreign key | Two live passwords on one account, only one carrying the failure counter |
| `CHECK ((tenancy = 'OPERATOR') = (company_uid IS NOT NULL))` | Operator staff with no company, and platform staff with one. Written as an equivalence so neither half can be satisfied alone |
| `FOREIGN KEY (staff_identity_id, company_uid)` on memberships | **One credential reaching two companies' data** |
| `UNIQUE (staff_identity_id, operator_uid)` | Unlinking removing one of two rows, leaving access the caller was told they lost |

### The cross-company guard

A staff member may serve **many operators** — one account, one password, one audit trail, which is how a
shared-services employee covering two depots is represented — but **only within one company**. Holding
memberships across two companies would mean one credential reaching two unrelated businesses' data: a
cross-tenant breach needing no exploit, just a mis-click on an admin screen.

That rule is a **composite foreign key**, not a service check. `staff_identities` carries a `company_uid`
and a `UNIQUE (id, company_uid)` for the key to target; every membership carries the same value and
references the pair. Postgres refuses a mismatched row outright — not from this application, not from a
data fix, not from a future admin surface that forgot to check.

Platform staff holding no memberships falls out of the same constraint rather than needing its own: their
`company_uid` is null and a membership's is `NOT NULL`, so no value would match. That is correct — they
reach every operator already.

`operator_uid` and `company_uid` are **bare handles** into the `tenancy` module: no foreign key, never
joined. A constraint there would invert the dependency arrow. The cost is that nothing detects a stale
handle, so it must fail closed wherever it is resolved.

### The trail

`auth_audit_events` records what happened on the authentication path — sign-ins, lockouts, role changes,
provisioning, withdrawals, membership changes. Two properties make it worth having:

- **It is written on paths that then reject the request.** The recorder runs in its own transaction
  (`REQUIRES_NEW`), so the record of a failure does not roll back with the failure. Without that the trail
  is emptiest exactly when it is most wanted.
- **Its principal columns are nullable**, so an attempt naming nobody who exists is still recorded. A run
  of them against `admin`, `administrator`, `root` is what a spray looks like, and it is invisible if only
  resolved accounts are kept.

Recording never throws and never fails a request. A trail that can cause an outage is a trail that gets
removed from the request path the first time it does.

**Repository lookups must be case-insensitive.** A case-sensitive query does not fail against a functional
index — it silently finds nothing, and the person is told their credentials are invalid with no error
anywhere explaining why.

`uid` has **no database default**: it is minted in Java at construction so it exists before flush, which is
what lets `equals`/`hashCode` use it.

## Rules a later slice must not break

These are behaviours, not preferences. Each has a test.

1. **Lockout is checked before the password.** A lock that still evaluates the password stops nothing.
2. **Account status is checked after it**, so a suspended account is indistinguishable from a wrong one.
3. **Refusals stay identical** — including timing. An unknown identifier still pays the hashing cost.
4. **Failure side effects must survive the rejection.** The service carries
   `@Transactional(noRollbackFor = ApiException.class)`; without it the counter rolls back with the throw,
   the lockout never triggers, and *nothing anywhere fails*.
5. **A configuration may only be switched off if nothing would quietly take its place.** Security has a
   framework default; persistence does not. Gating the filter chain off once produced a context where
   Boot's default chain served every route behind a generated password.
6. **`@EnableMethodSecurity` stays beside the filter chain.** Absent, every `@PreAuthorize` in the reactor
   is inert - present, reviewed, and doing nothing - and no test fails, because a test expecting 200 still
   gets one.
7. **A permission denial is rendered 403 by an explicit handler.** Method security throws from *inside* the
   controller invocation, so the chain's access-denied handler never sees it. Without a dedicated handler
   every refusal becomes a 500 with a stack trace at ERROR, and "you may not do that" is indistinguishable
   from an outage.
8. **`hasAuthority(...)` must never appear anywhere in the reactor.** ROOT carries no authorities, so the
   first bare expression merged locks the break-glass identity out of the system it exists to rescue.
9. **Archived roles are filtered at resolution**, not merely blocked at grant time. Otherwise archiving
   withdraws nothing from existing holders and the role keeps conferring everything it ever did.
10. **Grants are listed explicitly, never by pattern.** A role defined as "everything matching `%.READ`"
    turns a rename into a privilege escalation.
11. **An empty operator list is restrictive, always.** `filter()` returns a sentinel rather than an empty
    collection, and the resolver refuses rather than returning an empty scope. The opposite reading is one
    `isEmpty()` away and is unrestricted access.
12. **List endpoints filter in the query, never afterwards.** Fetching everything and discarding what the
    caller may not see is right until the endpoint is paged, at which point page one of a hundred rows
    filtered down to three looks like a total of three.
13. **Audit recording never throws and never fails a request.** It runs `REQUIRES_NEW` so the rows that
    matter most — the ones describing rejected requests — survive the rejection.
14. **Handlers are `public`.** Spring's method-security proxy does not advise a package-private method, so
    a gated package-private handler is a silent no-op: the annotation is present, the rule reads as
    enforced, and the door is open.
15. **Every `@PreAuthorize` concatenates a `Permissions` constant**, never a string literal. SpEL is not
    compiled, so a typo inside the quotes is a permission nobody holds — the route refuses everyone
    forever, and no test catches it.
16. **The envelope's `statusCode` is the response's status.** The advice sets it, so a handler returning
    `ApiResponse.created(...)` gets a real 201 rather than a body that contradicts the transport on the one
    field `success` is derived from.

## Configuration

| Key | Default | Absent behaviour |
|---|---|---|
| `identity.jwt.secret` | a local-only value | **Fails at startup** below 32 bytes |
| `identity.jwt.access-token-ttl` | `PT15M` | — |
| `identity.bootstrap.root.password` | *(blank)* | **No ROOT is created**, and nobody can sign in |

The blank bootstrap password is deliberate: a well-known fallback is discovered once and then works
everywhere it was never changed. A system with no way in is safer than a system with a shared default way
in.

The token carries only the uid and principal kind — **not** status, tenancy or later permissions. Anything
baked into a token is a snapshot, correct at issue and increasingly stale; a suspended account would keep
working until its token expired. That is the argument for the short TTL.

## Running it

Requires PostgreSQL. The default points at **port 15432**, not 5432 — on a machine running several
projects, 5432 is whatever container claimed it first, and pointing there would run these migrations
against somebody else's database.

```bash
docker exec <pg> psql -U admin -d postgres -c "CREATE DATABASE bus_core;"
IDENTITY_BOOTSTRAP_ROOT_PASSWORD=... mvn -pl services/bus-core -am spring-boot:run
```

Integration tests need Docker; they start their own `postgres:18-alpine` and never touch a shared
instance.

## The catalog

Permission codes are declared in `Permissions` **and** seeded by `R__seed_rbac.sql`, and a test asserts the
two agree in both directions.

That duplication is deliberate. **A code declared but not seeded refuses everyone, forever, and silently**
- the permission does not exist to be granted, so no role can hold it. No integration test finds it
either, because a test runs as an administrator granted every *seeded* code, or as ROOT which bypasses the
check. The catalog test is the only thing that catches it.

Ten codes today: `ROLE.READ` · `ROLE.GRANT` · `ROLE.REVOKE` · `PERMISSION.READ` · `STAFF.READ` ·
`STAFF.CREATE` · `STAFF.SUSPEND` · `STAFF.RESTORE` · `STAFF.OPERATOR_LINK` · `STAFF.OPERATOR_UNLINK`.

Granting and revoking are **separate codes**, and so are suspending and restoring, and linking and
unlinking. The rule is that widening access and narrowing it are different powers: during an incident there
are people who should be able to do one and not the other.

Seeded roles:

| Role | Holder | Carries |
|---|---|---|
| `PLATFORM_ADMIN` | `ADMIN` | every code |
| `SUPPORT` | `ADMIN` | the three read codes |
| `OPERATOR_ADMIN` | `OPERATOR` | the staff-administration codes, and `ROLE.READ` |

**A role is declared for one class of staff**, and granting it to another is refused. `OPERATOR_ADMIN`
exists because without an `OPERATOR`-held role no operator account could hold any role at all — every
routine staffing change at every operator would be a support ticket. It carries the same
staff-administration codes as `PLATFORM_ADMIN` and is not thereby equivalent to it: a permission says what
a caller may do, and the service decides to whom.

**ROOT holds no role and appears nowhere in the seed** - its authority is a single branch in the guard, and
seeding it a role would make that branch look redundant and invite its removal.

## What is left

Slices 1-5 of 12 are done, and **the other 16 modules are unblocked** — `OperatorScope` was the gate, not
slice 12. Everything remaining serves this module's own users and blocks nobody.

| Slice | What it adds |
|---|---|
| 6 | Credential lifecycle — set the first password, rotate, forced change, reset |
| 7 | Agent identity — PIN authentication, and the second audience the gate was built for |
| 8 | Rate limiting at the door |
| 9 | Transaction PIN, for value-moving operations |
| 10 | Multi-factor authentication |
| 11 | API clients — machine callers that re-prove a key per request and hold no session |
| 12 | Contract profile |

Slice 6 is the immediate one: accounts are provisioned `PENDING` with no credential, so today an
administrator can create an account that nobody can ever sign in to.
