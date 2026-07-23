# 12 · API conventions

*Assumes [00-glossary.md](00-glossary.md).*

The wire contract every endpoint honours. These are decisions, not defaults — a surface that varies is one
every client must implement twice.

## One envelope, always

**Every response uses the same shape, with every key present, on success and on failure alike.**

```json
{
  "success": false,
  "statusCode": 404,
  "code": "MERCHANT.NOT_FOUND",
  "message": "Merchant not found",
  "data": null,
  "errors": [],
  "meta": null,
  "traceId": "01JQ8F3K2M9X"
}
```

| Field | Type | Always present | Rule |
|---|---|---|---|
| `success` | boolean | ✓ | **Derived from `statusCode`, never set by hand.** Two fields encoding one fact will disagree the day someone sets one and forgets the other. |
| `statusCode` | int | ✓ | Mirrors the HTTP status. Present because responses get logged, proxied and batched, where the transport status is gone. |
| `code` | string | ✓ | `OK` on success, `DOMAIN.CONDITION` on failure. **This is the contract.** |
| `message` | string | ✓ | For humans. Reword and localise freely; never branch on it. |
| `data` | T \| null | ✓ | The payload. A list for collections. `null` on failure. |
| `errors` | array | ✓ | **Always an array**, empty when there is nothing to report. |
| `meta` | object \| null | ✓ | Pagination and nothing else. `null` on non-paged responses. |
| `traceId` | string | ✓ | Ties this response to a log line. |

**Optional keys are how a surface grows a second shape.** A key that is sometimes absent forces every client
to test for it, and the first endpoint that omits a different key has invented a second envelope nobody
declared. Present-and-null costs a few bytes and removes the whole class of problem.

## Error codes

`DOMAIN.CONDITION` — uppercase, dot-separated, naming the *condition* rather than the remedy:

```
MERCHANT.NOT_FOUND      SCOPE.NOT_AUTHORISED      AUTH.INVALID_CREDENTIALS
BOOKING.SEAT_TAKEN      VALIDATION.FAILED         AUTH.ACCOUNT_LOCKED
```

**A released code may be added to, never repurposed and never renamed.** A client branches on it, support
routes on it, a dashboard counts it. Changing what one means is a silent breaking change to every caller,
and nothing in the build will catch it.

**Distinct causes get distinct codes.** When a caller is refused because they lack a permission, because
they are the wrong kind of caller, and because the row belongs to someone else, those are three different
problems with three different fixes — a client that cannot tell them apart cannot act on any of them.

Never make a client parse `message` to work out what happened. If they have to, the code is missing or too
coarse.

## Validation errors

Field errors go in `errors` **in the same envelope**. There is no separate validation response type.

```json
{
  "success": false, "statusCode": 400,
  "code": "VALIDATION.FAILED",
  "message": "Validation failed",
  "data": null,
  "errors": [
    { "field": "amount",  "code": "MIN",               "message": "must be greater than 0" },
    { "field": "amount",  "code": "SCALE",             "message": "at most 2 decimal places" },
    { "field": null,      "code": "CURRENCY_MISMATCH", "message": "wallet currency differs from the fare" }
  ],
  "meta": null,
  "traceId": "01JQ8F3K2M9X"
}
```

A **list of objects**, not a map of field to message. A map cannot express two problems on one field, and
has nowhere to put an error that is not about a field at all.

**The shape must not depend on how the validation was implemented.** A framework-raised constraint violation
and a hand-thrown domain rule are the same thing to a caller, and must produce the same response. Where they
differ, a client's error handling silently depends on a server-side implementation detail — and will miss
every error raised the other way.

Report **all** failures, not the first. A form that surfaces one error at a time makes the user submit five
times to learn five things.

## Pagination

Nested under `meta`. **One shape; there is no flat variant.**

```json
{
  "success": true, "statusCode": 200, "code": "OK", "message": "Success",
  "data": [ ],
  "errors": [],
  "meta": { "pageNumber": 0, "pageSize": 20, "totalElements": 137, "totalPages": 7, "last": false },
  "traceId": "01JQ8F3K2M9X"
}
```

Nesting keeps `data` a clean array and gives pagination room to grow — a cursor, an approximate-total flag —
without adding top-level keys that mean nothing on the other 90% of responses.

If a total is ever expensive enough to approximate or omit, that must be **visible in `meta`**, not left for
a client to discover when their page controls misbehave.

Paging inputs are validated in one place (see the shared kernel's paging facility). An unknown sort property
is **refused**, not silently dropped: returning arbitrarily-ordered results to a caller who asked for an
order is worse than an error, because nothing looks wrong.

## traceId

Present on every response, success or failure. It is the difference between a user saying "I got an error"
and someone finding the exact log line. It costs one field.

## What this rules out

| Not allowed | Because |
|---|---|
| A second wrapper type for any case | Four wrapper types means four parse paths, and the discriminator ends up being *which endpoint you called* rather than anything in the payload. |
| `errors` replacing `data` | A client parsing `data` gets nothing, and only for the failures that happen to be raised one particular way. |
| A flat pagination variant alongside the nested one | Half-migrated is the worst state: clients implement both forever, and nobody can tell which endpoints are which without trying them. |
| Branching on `message` | It is human text. The moment a client string-matches it, it can never be reworded or translated. |
| Setting `success` independently of `statusCode` | Redundant state that can contradict itself. |
| `204 No Content` | A void operation returns `200` with `data: null`, so the envelope is never absent and a client never needs a second path for "no body". |

## Migrating an existing surface

Emit the new envelope everywhere, keep the old pagination fields **duplicated** alongside `meta` for one
release so existing clients keep working, then delete them on a stated date.

A deprecation with a date is a migration. A deprecation without one is a permanent second shape.
