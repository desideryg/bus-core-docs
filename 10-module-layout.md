# 10 · Module layout

*Assumes [00-glossary.md](00-glossary.md).*

Every module under `modules/` has the same shape.

## The one rule

**A module's package root is its published surface. Everything else lives under `internal/`.**

```
modules/<module-name>/
├── pom.xml
└── src/main/java/tz/co/otapp/buscore/<modulename>/
    ├── package-info.java          ← published: ports, value objects, enums other
    │                                 modules may import. Nothing else.
    └── internal/
        ├── package-info.java
        ├── api/                   HTTP surface, split by audience
        │   ├── admin/               /admin/v1/**
        │   └── agent/               /agent/v1/**
        ├── config/                @Configuration — see "the scan contract" below
        ├── domain/
        │   ├── entity/            JPA entities
        │   ├── dto/               request/response bodies, projections
        │   └── enums/             closed sets this module stores
        ├── repository/            Spring Data repositories
        ├── security/              permission constants, guards
        └── service/               interfaces
            ├── command/           multi-field service inputs
            └── impl/              implementations
```

Add `src/main/resources/db/migration/<modulename>/` when the module owns its first table, and
`src/test/java/...` mirroring the internal tree when it grows its first test. Neither exists until then —
an empty directory is not tracked by git and communicates nothing.

## Publishing is a deliberate act

Anything created under `internal/` is hidden by default. To publish a type, **move it up** to the package
root. There is no annotation, no modifier, no configuration — the location *is* the decision, which is why
it survives review.

Enforced three ways, in increasing order of stubbornness:

1. **Maven.** A module that does not declare a dependency cannot import the other at all.
2. **`ModuleBoundaryTest`.** No class outside `…<module>` may depend on `…<module>.internal..`. This is
   what stops a *declared* dependency reaching past the published surface.
3. **`ModuleDependencyTest`.** Reads bytecode, because Maven puts a module's whole transitive closure on
   its compile classpath — declare one module and you can silently import everything it depends on.

## The scan contract

`BusCoreApplication` component-scans `tz.co.otapp.buscore` but **excludes everything under `internal/`
except `internal.config`**:

```java
pattern = "tz\\.co\\.otapp\\.buscore\\..*\\.internal\\.(?!config\\.).*"
```

So the assembler finds each module's configuration and nothing else; that configuration registers the
module's own beans, entities and repositories.

This indirection is load-bearing and **invisible to the architecture rules**, because a component scan
crosses a boundary by *string*, not by type reference. Without the exclusion, a configuration annotated
`@Profile` would decide nothing — the assembler would already have registered the beans it was gating.

The rule is stated as "not config" rather than as a list of the packages that exist today, because a list
has to be edited every time a module grows a package, and the edit that is forgotten does not fail — it
silently widens the scan.

**Practical consequence:** a `@Service` not reachable from a configuration in `internal/config` is not
registered. That is the design working, not a bug.

## What belongs in each package

| Package | Holds | The rule that bites |
|---|---|---|
| *(root)* | ports, value objects, published enums | If another module names it, it lives here. Nothing else does. |
| `internal/api/<audience>` | controllers + delegates | Controllers hold no logic — a thin shim over a delegate. Mappings are **relative**; the `/api` prefix comes once from the context path. |
| `internal/config` | `@Configuration` | The only package the assembler reaches. |
| `internal/domain/entity` | JPA entities | Changes only alongside a migration. No cross-module foreign keys. |
| `internal/domain/dto` | wire shapes, projections | **This is where a module's request and response types live** — not in `api-contracts`, until a second module needs one. Carries data, never authority. Keep separate from entities even when identical: they diverge the first time a column must not be returned. |
| `internal/domain/enums` | closed sets | Persist the **name**, never the ordinal. Renaming a constant is a migration, not a refactor. |
| `internal/repository` | repositories | A lookup must match the index that guarantees it — a case-sensitive query against a `lower()` index silently bypasses uniqueness. |
| `internal/security` | guards, filters, hashers | Hashing follows *how* a secret is used: looked-up → deterministic, verified → adaptive, recomputed → encrypted. |
| `internal/service` | interfaces | Keep narrow. No module-wide facade — a caller needing one operation must not compile against all of them. |
| `internal/service/command` | inputs | Named fields, so two arguments of the same type cannot be transposed. |
| `internal/service/impl` | implementations | Ordering inside a flow is frequently the security property, not a detail. |

## Handlers must be public

Spring's method-security proxy **does not advise a package-private method**. A gated handler that is
package-private is a silent no-op: the annotation is present, the rule is green, and the door is open.

This is not hypothetical — in the reference implementation every controller handler was package-private
before an audit caught it, meaning the entire authorization layer could have been decorative.

## Joining the deployable

A module builds in the reactor from the day it is scaffolded, but it is **not** a dependency of
`services/bus-core` until its first slice lands. Adding that `<dependency>` is the *last* step of a slice,
not the first.
