# 40 · identity-access

*Assumes [00-glossary.md](00-glossary.md), [10-module-layout.md](10-module-layout.md),
[11-naming.md](11-naming.md), [12-api-conventions.md](12-api-conventions.md),
[21-inter-module-communication.md](21-inter-module-communication.md).*

**This describes code that exists**, unlike the 30-series study of a different codebase. It is updated
as each slice lands.

**Status: slices 1-2 of 12 complete.** Staff can sign in, and routes can be gated on permissions.

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
| `Principal` | `record(uid, type, tenancy, permissions)` | know who is acting |
| `PrincipalType` | `STAFF` | branch on the kind of actor |
| `PrincipalContext` | `Principal require()` · `Optional<Principal> current()` | obtain the acting principal |
| `StaffTenancy` | `ROOT · ADMIN · OPERATOR · PARTNER` | know which organisation they belong to |
| `Permissions` | `DOMAIN.ACTION` constants | name a permission on a route |
| `PermissionGuard` | the bean `@perm` | gate a route |

```java
// who is acting
Principal actor = principalContext.require();   // throws 401 if unauthenticated

// gate a route - concatenate the constant, never write the literal
@PreAuthorize("@perm.has('" + Permissions.ROLE_GRANT + "')")
public ApiResponse<Void> grant(...) { ... }
```

**No operator scope yet** — that is slice 5. Until it lands a module can ask *who* and *what may they
do*, but not *whose rows*: a read that should be limited to one operator's data cannot be limited yet.

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

Seeded roles: `PLATFORM_ADMIN` (all five codes) and `SUPPORT` (the three read codes). **ROOT holds no role
and appears nowhere in the seed** - its authority is a single branch in the guard, and seeding it a role
would make that branch look redundant and invite its removal.

## What is left

Slices 1-2 of 12. Next: **the audience gate** (slice 3), which distinguishes staff routes from agent routes
at the door. It will appear to do nothing, because there is only one audience - which is exactly why it
lands now rather than being retrofitted once there are two.

`OperatorScope` arrives in **slice 5**, and that is the point at which the other 16 modules are unblocked -
not slice 12. Slices 6-12 serve this module's own users and block nobody.
