# 40 · identity-access

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[11-naming.md](11-naming.md), [12-api-conventions.md](12-api-conventions.md),
[21-inter-module-communication.md](21-inter-module-communication.md).*

**This describes code that exists**, unlike the 30-series study of a different codebase. It is updated
as each slice lands.

**Status: slice 1 of 12 complete.** Staff can sign in and be recognised. Nothing else works yet.

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
| `Principal` | `record(UUID uid, PrincipalType type)` | know who is acting |
| `PrincipalType` | `STAFF` | branch on the kind of actor |
| `PrincipalContext` | `Principal require()` · `Optional<Principal> current()` | obtain the acting principal |

```java
// in any module that declares a dependency on identity-access
Principal actor = principalContext.require();   // throws 401 if unauthenticated
```

That is the entire published surface. **No permission checking and no operator scope yet** — those are
slices 2 and 5, and until they land a module cannot ask "may they" or "whose rows", only "who".

`Principal` carries no `Long` id, and never will: the numeric key does not cross a module boundary.

## The doors

| Method | Path | Auth | Returns |
|---|---|---|---|
| `POST` | `/api/admin/v1/auth/login` | public | token, expiry, display name |
| `GET` | `/api/admin/v1/auth/me` | bearer | the signed-in account |

Public means *presents its own credential*. Everything else is `authenticated()` by default, so a route
added tomorrow is protected by omission rather than by someone remembering.

### Error codes

| Code | Status | Meaning |
|---|---|---|
| `AUTH.INVALID_CREDENTIALS` | 401 | **Unknown identifier, wrong password, or any non-active account** |
| `AUTH.ACCOUNT_LOCKED` | 423 | Too many consecutive failures |
| `AUTH.PASSWORD_CHANGE_REQUIRED` | 409 | Correct password, but it must be rotated. **No token issued** |
| `AUTH.NOT_AUTHENTICATED` | 401 | No usable token on a protected route |

**One code covering three causes is the point, not laziness.** If an unknown username and a wrong
password answered differently, the sign-in endpoint would be a free tool for discovering which accounts
exist. The refusal is identical, and the code even spends the hashing time on an identifier that does not
exist so the *timing* does not distinguish them either.

`ACCOUNT_LOCKED` is the one deliberate exception. It leaks existence — five failures against a guessed
username reveals the account is real — and is accepted because these are internal staff usernames, and an
employee told only "credentials not valid" retries, deepens the lock, and calls support. **If this surface
ever serves public self-registration, revisit that first.**

## The schema

Two tables, and the constraints are the interesting part.

| Constraint | Defeats |
|---|---|
| `UNIQUE (tenancy) WHERE tenancy = 'ROOT'` | Two concurrent bootstraps both seeing "no ROOT" and both inserting. A service check cannot prevent it — both transactions see the same empty table |
| `UNIQUE (lower(username))`, same for email | `Alice` and `alice` as two accounts, while display casing survives |
| `UNIQUE` on the credential's foreign key | Two live passwords on one account, only one carrying the failure counter |

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

## What is left

Slice 1 of 12. Next: **RBAC** (slice 2), which must land before any gated route exists anywhere — a
permission that is annotated but not seeded refuses everyone but ROOT, forever, and no integration test
catches it.

`OperatorScope` arrives in slice 5, and that is the point at which the other 16 modules are unblocked.
Slices 6–12 serve this module's own users and block nobody.
