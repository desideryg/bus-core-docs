# 11 · Naming

*Assumes [00-glossary.md](00-glossary.md).*

## Modules and packages

Module directories are **kebab-case and singular in concept**: `identity-access`, `seat-inventory`,
`wallet-ledger`. The Java package is the same name **with the dashes stripped**:

```
modules/seat-inventory  →  tz.co.otapp.buscore.seatinventory
modules/agent           →  tz.co.otapp.buscore.agent
```

That mapping is *computed* by `ModuleCatalog.packageRootOf`, so a module whose directory and package
disagree is invisible to every architecture rule. It is not a convention you may bend.

**Maven coordinates mirror the base package.** groupId is `tz.co.otapp.buscore`; the artifactId is the
module directory name. When the two drift apart, a dependency reads as one thing and its code says
another.

## The naming rule that prevents collisions

**This system separates the *person* from their *login*, and they live in different modules.** So:

```
staff module    → Staff            the employee
agent module    → Agent            who they sell for, under what scope
identity module → StaffIdentity    may this login work
                  AgentIdentity
                  StaffCredential  the secret
                  AgentCredential
```

Naming the identity aggregate `Staff` or `Agent` would collide with the module that legitimately owns that
person. `<Party>Identity` + `<Party>Credential` states the boundary in the type name and keeps the two
parallel aggregates symmetric.

## Types

| Kind | Convention | Example |
|---|---|---|
| Entity | Singular noun, no suffix | `Session`, `Permission` |
| Join entity | Both sides, in dependency order | `RolePermission`, `StaffRole` |
| Port (offered) | Noun or noun phrase, no `I` prefix | `PrincipalContext`, `StorageFiles` |
| Port (inbound) | Says what it *looks up* or *does* | `OperatorTenancyLookup`, `SmsNotifier` |
| Implementation | Port name + `Impl`, under `internal` | `OperatorTenancyLookupImpl` |
| Controller | `<Thing><Audience>Controller` | `StaffAdminController` |
| Delegate | Same, `Delegate` | `StaffAdminDelegate` |
| Command | Verb phrase or `New<Thing>` | `NewAgentIdentity` |

**Never abbreviate in a type name.** `TransactionPin…`, not `TxnPin…`. The reference implementation carries
both spellings for one feature in one package, which is exactly the confusion the rule prevents.

**Name a pair on one axis.** If two ports are siblings, name them both for the channel or both for the
purpose — `EmailNotifier` / `SmsNotifier`, not `CredentialNotifier` / `SmsNotifier`. A mixed axis makes one
look like the general case and the other like a special case when they are peers.

**Do not reuse a standard term for a different meaning.** `audience` is the JWT `aud` claim — the intended
recipient of a token. Using it to mean "kind of client" misleads precisely the readers who know the
standard. Coin a new word instead: `clientKind`.

## Fields

| Kind | Convention | Note |
|---|---|---|
| Instant | `<verb>At` | `expiresAt`, `consumedAt`, `revokedAt`, `issuedAt`, `occurredAt`, `usedAt` — **no exceptions** |
| Stored secret | `<what>Hash` | `passwordHash`, `tokenHash`. Makes "this is not the secret" visible at the call site |
| Boolean | `is…` / `must…` / past participle | `mustChangePassword`, `activated` |
| Cross-module reference | `<module-thing>Uid` | `operatorUid`, `principalUid`. The `Uid` suffix marks it as a handle with no FK |
| Counter | `<what>Count` | `failedLoginCount` |

## Enums

Persisted as **`EnumType.STRING`**. The constant name *is* the stable code and stored history is read back
by it, so a constant may be **appended** but never renamed or reordered. A display label is a separate
field and may be reworded freely.

Name the enum for **what it holds**, not for where it hangs. If the javadoc has to work hard to explain
what the name does not say, the name is wrong — `StaffTenancy` rather than `UserType`.

A `purpose`, `status`, `kind` or `channel` is a closed set. Make it an enum on first use; a free-form
`String` beside an enum of the same name in a sibling table is a defect waiting to be written.

## Database

| Object | Convention | Example |
|---|---|---|
| Table | `snake_case`, plural | `staff_identities`, `role_permissions` |
| Column | `snake_case` | `failed_login_count`, `operator_uid` |
| Unique index | `ux_<table>_<columns>` | `ux_staff_identities_username_lower` |
| Plain index | `ix_<table>_<columns>` | `ix_sessions_principal_uid` |
| Check constraint | `ck_<table>_<what_it_asserts>` | `ck_credential_tokens_purpose_matches_principal` |
| Sequence | `<thing>_seq` | `invoice_number_seq` |

Every table carries `id`, `uid`, `created_at`, `updated_at` from the shared base entity. Timestamps are
plain `timestamp` holding UTC, never `timestamptz`.

## Permissions

`DOMAIN.ACTION`, uppercase, dot-separated, singular domain:

```
VEHICLE.READ    SCHEDULE.PUBLISH    USER.INVITE    ROLE.GRANT
```

The domain is the thing acted on, not the module. Keep them greppable — a permission code is the one string
a reviewer will search the whole repo for.

> **Never make a permission code's meaning depend on its punctuation.** Granting by pattern (`LIKE '%.READ'`)
> turns a rename into a privilege escalation: a code renamed from `CREDENTIAL_READ` to `CREDENTIAL.READ`
> silently joins the granted set. Grant by explicit membership.

## API paths

Relative in the controller; the `/api` context path is applied once, globally.

```
/admin/v1/**       staff audience
/agent/v1/**       agent and machine audience
/callbacks/**      external inbound
```

**The controller's package and its mapped prefix must agree** — a controller under `internal/api/admin`
mapping an agent path is behind the wrong door, and that is a rule worth enforcing rather than reviewing.

URLs address rows by **uid**, never by id: `/uid/{uid}`.
