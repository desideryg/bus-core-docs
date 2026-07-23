# 30 · Reference study — identity-access

> ## ⚠ THIS DESCRIBES A DIFFERENT CODEBASE
>
> This document studies **`../../BUS4/core-bus-api`**, an earlier and separate implementation.
>
> **None of the code described here exists in `bus-core-api`.** Do not follow file paths from this document
> expecting to find them. Do not treat any of it as a description of the current project's state.
>
> It is here because that system solved these problems already and its reasoning is worth having. The
> normative rules are [00-glossary.md](00-glossary.md) through
> [21-inter-module-communication.md](21-inter-module-communication.md).
>
> Package names below use that project's convention (`tz.co.otapp.identityaccess`), **not ours**
> (`tz.co.otapp.buscore.identityaccess`).

*Assumes [00-glossary.md](00-glossary.md), [11-naming.md](11-naming.md),
[20-module-catalog.md](20-module-catalog.md), [21-inter-module-communication.md](21-inter-module-communication.md).*

Scale, for calibration: 192 files, ~12,785 LOC, 20 published types, 17 tables, 19 migrations, 65 endpoints,
193 permission codes. 17 of 28 modules depended on it.

## What it answered

Three questions, plus the credential lifecycle behind all three:

| Question | Mechanism |
|---|---|
| Who is acting? | authentication of staff, agents, machines → `Principal` |
| What may they do? | the RBAC catalog → a permission guard bean |
| Whose rows may they touch? | `OperatorScope` |

The last two are independent and **both always ran**. A platform administrator reaching every operator's
vehicles still needed `VEHICLE.READ` to read one.

It deliberately owned **no business linkage**: agent selling authority lived in a separate module with an
independent lifecycle, and passenger identity in another again.

## The ideas worth carrying over

### The permission guard is reached by name

A `@Component("perm")` called from SpEL: `@PreAuthorize("@perm.has('VEHICLE.READ')")`. Because it is
resolved by **bean name**, no module gains a compile-time dependency on the identity module — 342 call
sites across 21 modules, zero imports.

It deliberately rejected the obvious alternative. A bare `hasAuthority('VEHICLE.READ')` would have worked
with zero new code, and that was the trap: it scatters a hundred authorization decisions with no single
point of interpretation, which makes the break-glass bypass unimplementable.

### The break-glass identity is one `if`, in code

`ROOT` held no role and appeared nowhere in the permission seed; its authority was a single line inside the
guard — *"in code, where no migration can revoke it and no token-minting path can forget it."* Consequently
the first raw `hasAuthority(...)` merged anywhere would have locked it out of the system it exists to
rescue.

### Emptiness is always restrictive

`OperatorScope` carried a `platform` boolean and a list of operator uids. **The boolean, not the list, is
what widens a read** — both a platform scope and a broken scope have an empty list, so code keying off
emptiness gets it exactly backwards.

Three independent places enforced this: the resolver checked tenancy *before* reading the list; staff bound
to no operator got a hard refusal rather than everything; and the query filter returned a sentinel uid that
matches nothing rather than an empty list. The dangerous shape — `if (list.isEmpty()) skip the WHERE
clause` — turns "names no operator" into "sees everything".

### Authority never comes from a body

The one place a caller named an operator was a **query parameter**, validated against their scope, so it
selected among operators they already reached and could never widen them.

### Hashing follows how a secret is used

Looked-up secrets (refresh tokens, API keys) → deterministic SHA-256, so lookup is one indexed read.
Verified secrets (passwords, PINs, API secrets) → bcrypt. Recomputed secrets (a TOTP seed) → AES-GCM
encryption, because they cannot be hashed at all.

An earlier design bcrypt'd the API key, which cannot work: bcrypt differs on every call, so the lookup
would have matched nothing, ever.

### The database is the arbiter

The load-bearing constraints were partial and functional indexes, each defeating a race that a
`SELECT`-then-`INSERT` cannot:

| Constraint shape | Defeats |
|---|---|
| `UNIQUE (user_type) WHERE user_type = 'ROOT'` | Two break-glass identities from concurrent bootstraps. |
| `UNIQUE (principal_uid, purpose) WHERE consumed_at IS NULL` | Accumulating valid invitation links, where the oldest leaked one still opens the account. |
| `UNIQUE (lower(username))` | `Root` and `root` as two accounts — while preserving display casing. |
| `UNIQUE` on a 1:1 foreign key | Two live passwords on one account, only one subject to lockout. |
| `CHECK` binding a purpose to a principal kind | A password-reset token minted for an account type that has no password. |

### Failure side effects must survive the rejection

Nine methods carried `@Transactional(noRollbackFor = ApiException.class)`. A plain `@Transactional` rolls
back the lockout counter, the attempt count and the audit row *along with* the throw — silently disabling
lockout and erasing the forensic trail.

### The identifier is never an oracle

Unknown identifier, wrong secret, and non-active account all answered identically. A distinguishable
refusal tells an attacker which accounts exist.

### Lockout is checked before the secret

*"A lock that let the right PIN through would stop nothing — the attacker's last guess is the one that
matters."*

### MFA cannot be bypassed by construction

A correct password on an MFA-enabled account returned a type in which, when a challenge is required, **there
are no token fields to populate**. The step-up could not be skipped by forgetting a check, because there was
nothing to forget.

### Refresh reuse triggers a wide revocation

Presenting an already-rotated refresh token revoked **every** live session for that principal, not just the
leaked lineage — *"a leaked refresh token is strong enough evidence of compromise that failing safe across
all the principal's devices beats failing narrow."*

### Three gates, three distinct refusals

Audience, permission, and tenancy each failed with their own error code, because each has a different
remedy — *"a client that cannot tell them apart cannot route a support ticket."* Tenancy is the quiet one:
on a list endpoint it does not refuse at all, it just returns fewer rows.

## What it got wrong

Six verified defects, the two most serious being an unmetered credential-exchange endpoint with no lockout,
no rate limit and no failure audit; and a deployment role that registered every controller while its
security configuration did not register at all.

They are catalogued, with the rule that prevents each, in the build plan that follows this document — not
linked from here, because a link forward would be the first edge of a cycle.
