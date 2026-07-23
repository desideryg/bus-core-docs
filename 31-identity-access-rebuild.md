# 31 · Building identity-access

*Assumes [00-glossary.md](00-glossary.md) through
[30-reference-identity-access.md](30-reference-identity-access.md).*

The plan for `modules/identity-access` in **this** project. The package tree exists; no types do yet.

## Slice order

Smallest-that-boots first. Each slice ships entities, migrations, service, controller and config together.

| # | Slice | Adds | Why here |
|---|---|---|---|
| **1** | **Staff login end-to-end** | identities, credentials, sessions, JWT, the permission guard **with the break-glass bypass from day one** | The smallest thing that exercises every assembly seam at once: the scan exclusion, per-module Flyway, entity-manager ordering, fail-fast secrets. Proof: log in, get a bearer token, call `/users/me`. |
| **2** | **RBAC** | roles, permissions, both pivots, the seed, method security, the catalog test | **Must precede any gated controller.** A code that is annotated but unseeded refuses everyone but the break-glass identity, forever. |
| **3** | **Audience gate** | audience matchers on the two path prefixes | Needs only the principal kind. **Land it before the agent audience exists**, so the door is closed by construction rather than retrofitted. |
| **4** | **Auth audit** | the event table and recorder, plus `noRollbackFor` on every credential-comparing method | Retrofit is painful because that transaction setting must go on all of them at once. |
| **5** | **Staff administration + tenancy** | operator memberships, `OperatorScope`, the resolver, the inbound tenancy port | Where the cross-tenant invariants land. |
| **6** | **Credential lifecycle** | tokens with the check and partial unique index; invitation, temporary password, reset | Pulls in `notification`. |
| **7** | **Agent identity** | agent identity and credential, both counters, both locks, the SMS port | **Fix the initial-PIN defect here** — see below. |
| **8** | **Rate limiting** | the login limiter | First non-database dependency; fails open, so it can land late. |
| **9** | **Transaction PIN** | the port, the service, its own limiter | Get the counter-selection rule right — see below. |
| **10** | **MFA** | TOTP, recovery codes, OTP, challenges | Introduces the TOTP encryption key. Put it in the environment template. |
| **11** | **API clients** | key and secret, the authentication filter | Independent of 7–10. |
| **12** | **Contract profile** | stub configuration | **Last**, and only once the service interfaces stop moving — it is a hand-written mirror and every signature change costs an edit. |

## Entities

17, named per [11-naming.md](11-naming.md). `<Party>Identity` + `<Party>Credential`, because the person
themselves is owned by `staff` and their selling authority by `agent`.

| Cluster | Entities |
|---|---|
| Staff | `StaffIdentity`, `StaffCredential`, `StaffOperator` |
| RBAC | `Role`, `Permission`, `StaffRole`, `RolePermission` |
| Agent | `AgentIdentity`, `AgentCredential` |
| Session & MFA | `Session`, `StaffTotp`, `StaffRecoveryCode`, `StaffOtp`, `MfaChallenge` |
| Machine & audit | `ApiClient`, `CredentialToken`, `AuthAuditEvent` |

Enums: `StaffTenancy`, `AccountStatus`, `PrincipalType` published; `AuthEventType`,
`CredentialTokenPurpose`, `OtpChannel`, `OtpPurpose`, `ApiClientKind` module-private.

### Decisions taken up front

- **Real `@ManyToOne` everywhere**, including the MFA tables. The reference mixed associations and bare
  `Long` columns with nothing explaining the switch.
- **`@Column(length = …)` on every string**, matching the migration. `validate` compares type prefixes, not
  lengths, so a mismatch passes silently — and generated DDL would give an encrypted column too little room.
- **Counters incremented by atomic `UPDATE`**, not read-modify-write. Otherwise every attempt cap is
  bypassable by parallel requests. `@Version` is the *wrong* fix here: optimistic-lock failures on
  concurrent logins would deny service to legitimate users.
- **No `@OneToMany` inverses.** Never load an identity and get its sessions. On a table dominated by refresh
  events, a mapped collection is a loaded gun.
- **`StaffTenancy`, not `UserType`.** The name should say it means tenancy — not job function, not level in
  the operator tree. The reference spent four paragraphs of javadoc explaining what its name did not say.

## Defects observed in the reference — do not reproduce

These were verified against that codebase's source. They are listed because each is easy to recreate.

### 1 · An unmetered credential-exchange endpoint

The agent initial-PIN exchange compared the current PIN with **no lockout check, no failure counter, and no
audit row on failure** — the audit fired only on success. It was also absent from the rate limiter's path
list. The staff equivalent had both guards.

Result: anyone knowing one mid-onboarding username could walk all 10,000 PINs with no lockout, no rate
limit, and no trace.

**Rule for slice 7:** every endpoint that compares a credential gets the lockout check, the failure counter,
the audit row, and a rate-limit entry. All four, or it is not done. There is no such thing as a
credential-comparing endpoint that is exempt because it is "part of onboarding".

### 2 · A deployment role with controllers but no security

One profile registered every controller (its module config was gated on `!contract`) while the security
configuration did not register at all (gated on `api & !contract`), and no profile group mapped one to the
other. Starting the application in that role fell back to framework defaults: every route behind basic auth
with a generated password, no token filter, no audience gate, no tenancy.

**Rule:** the module configuration and the security configuration must carry the **same** profile
expression. If a role registers controllers, it registers the chain that guards them. Add a test that boots
each role and asserts a known route refuses anonymously.

### 3 · Archiving a role revoked nothing

The permission-resolution query did not filter on the archive timestamp, so existing grants kept appearing
in every holder's token indefinitely. Archiving blocked only forward operations.

### 4 · Granting by pattern

A role was granted every permission matching `LIKE '%.READ'`. Renaming an unrelated permission so that it
ends in `.READ` silently joins that set. **Grant by explicit membership.**

### 5 · Missing source IP on one login path

One of the two login paths passed a literal `null` for the client address, defeating the index on exactly
the population the audit trail called its primary detection surface.

### 6 · No locking on counters

No optimistic or pessimistic locking anywhere; every attempt cap was last-write-wins and bypassable by
parallel requests. The unique indexes were the only real backstop.

## Things the build should catch that it currently cannot

Worth adding as this module grows, because each is a hole no existing rule covers:

- **A gated handler that is not `public`.** Method-security advice does not apply to package-private
  methods, so the annotation is decorative. In the reference, *every* handler was package-private before an
  audit caught it.
- **A controller whose package and mapped prefix disagree.** In the reference this let a controller sit in
  a neutral package, map a reserved prefix, satisfy every boundary rule, and expose an operator's provider
  credentials to any agent.
- **A permission code that is gated but not seeded.** It refuses everyone but the break-glass identity, and
  no integration test catches it because tests run as a fully-granted or bypassing principal.
- **A native query naming another module's table.** See
  [21-inter-module-communication.md](21-inter-module-communication.md) — the architecture rules read
  bytecode, so SQL is invisible to all of them.
