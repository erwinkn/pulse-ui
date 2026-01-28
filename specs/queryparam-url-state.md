# QueryParam URL-synced State (Spec)

## Goal
Enable state attributes to sync bidirectionally with URL query params by annotating state fields with `ps.QueryParam[...]`.

## API
Use `ps.QueryParam[T]` in `ps.State` annotations.

```python
class Filters(ps.State):
    q: ps.QueryParam[str] = ""
    page: ps.QueryParam[int] = 1
    debug: ps.QueryParam[bool] = False
    org: ps.QueryParam[str | None] = None
    tags: ps.QueryParam[list[str]] = []
    since: ps.QueryParam[date] = date(2024, 1, 1)
    updated_at: ps.QueryParam[datetime] = datetime.now(timezone.utc)
```

## Behavior
- Init: if URL has param -> parse -> set state; else use class default.
- State->URL: setting property updates URL query param.
- URL->State: browser navigation or manual URL edit updates property.
- Removal: if value is `None` or equals default -> param removed.
- History: default `replace=True` to avoid history spam.
- No new JS protocol; use existing navigate/update messages.

## Binding Rules
- Only allowed when state instance is created in render context (route + render session). Else error on init.
- Bound to a single RouteContext (mount). Uses live route updates from that mount.
- Duplicate param key in the same mount -> error on init.

## Sync Model (no new JS)
- Use existing server message `navigate_to` to update URL.
- Use existing client `update` to send `routeInfo` back on navigation.
- Server side adds per-mount `QueryParamSync` manager:
  - Register bindings (key, signal, default, codec).
  - Effect A (URL->State): watches `route.info["queryParams"]`, parses, writes state with guard.
  - Effect B (State->URL): watches bound signals, builds new query map, `render.send({"type": "navigate_to", ...})`.
  - Guard: skip if serialized value unchanged or if change came from URL sync.

## Type Support (v1)
Supported base types:
- `str`, `int`, `float`, `bool`
- `date`, `datetime`
- `Optional[T]` (missing or empty => `None`)
- `list[T]` where `T` is any supported scalar (including `date`/`datetime`/`Optional[T]`)

Unsupported types -> error at class creation (StateMeta) or state init.

## Scalar Encoding
- `str`: raw
- `int`: `str(int)`
- `float`: `str(float)`
- `bool`: `true`/`false`
- `date`: ISO 8601 `YYYY-MM-DD`
- `datetime`: ISO 8601 `YYYY-MM-DDTHH:MM:SS[.ffffff][Z|+HH:MM]`

## Parsing Rules
- `int`: strict `int(value)`
- `float`: strict `float(value)`
- `bool`: accept `true/false/1/0` (case-insensitive)
- `date`: `date.fromisoformat(value)`
- `datetime`:
  - Accept `Z` by normalizing to `+00:00` before `datetime.fromisoformat`.
  - If parsed datetime is naive, warn and treat as UTC (`tzinfo=UTC`).

## Naive datetime behavior
- URL->State: warn on naive; set `tzinfo=UTC`.
- State->URL: warn on naive; serialize in UTC with `Z`.

## List Encoding (comma + escape)
- Encode list into a single param value.
- Escape each item string before joining:
  - `\` -> `\\`
  - `,` -> `\,`
- Join items with literal `,`.
- Empty list => remove param if it equals default; otherwise encode as empty string.

### List Parsing
- Split on commas **not escaped** by `\` after URL decoding.
- Unescape in each token:
  - `\\` -> `\`
  - `\,` -> `,`
- Trailing `\` or invalid escape -> error.
- Empty value => `[]`.

Notes:
- Commas inside items are supported via escape.
- Empty item becomes `""`; scalar parse then applies (non-string types may error).

## URL Building
- Base on current `route.queryParams`, override managed keys, remove params when needed.
- Preserve unrelated query params.
- Preserve hash. Path is current `route.pathname`.

## Errors
- Invalid parse -> raise with param name + expected type.
- Duplicate param key in same mount -> error on init.
- Unsupported types -> error on class creation or init.

## Tests (pytest)
- Init from URL overrides default.
- Missing param uses default; default value removed from URL on write.
- State->URL updates query, preserves other params.
- URL->State updates value, no navigate loop.
- Duplicate key raises.
- Date/datetime parse + serialize.
- Naive datetime warns and coerces to UTC.
- List encode/decode with commas and backslashes.
