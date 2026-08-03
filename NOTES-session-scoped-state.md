# Session-scoped `global_state` + session-owned `QueryParamSync`

> Filename note: the task asked for `NOTES.md`, but this repo already tracks a
> `notes.md` at the root with unrelated personal content, and macOS is
> case-insensitive — `NOTES.md` and `notes.md` are the same file. Writing
> `NOTES.md` would have destroyed it, so the audit lives here instead.

## Part 1 — `global_state` becomes purely render-session-scoped

### Decision

`ps.global_state(...)` never stores anything process-wide. Both branches of the
accessor route through `RenderSession.get_global_state`. `id=` is a *keying
discriminator within a session* (`f"{base_key}|{id}"`), not a scope switch.
The module-level `GLOBAL_STATES` dict is gone.

Consequences:
- No cross-user/cross-session sharing (that was an unintended multiplayer
  footgun: mutable UI selection state leaking between users).
- No process-wide leak: keyed instances now live in `RenderSession._global_states`,
  which `RenderSession.close()` clears *and* disposes — so keyed instances get
  disposal parity with non-keyed ones for free (verified: `close()` calls
  `value.dispose()` over `_global_states.values()`).
- The `id=` path now requires a render context (it previously did not touch
  `PulseContext` at all). Intended.

Cross-tab coordination for one user is the job of `UserSession`
(`user_session.py` + cookie/server `SessionStore`). Cross-user multiplayer is
explicitly unsupported; if it comes back it must be a distinct, explicitly named
primitive, never a side effect of passing `id`.

### Blast radius (grep over `packages/`, `examples/`, `tests/`, `docs/`, `skills/`, `tutorial/`)

`GLOBAL_STATES` references — all removed:
- `pulse/hooks/runtime.py`: dict definition, use in `accessor`, `__all__` entry.
- `pulse/__init__.py`: `GLOBAL_STATES as GLOBAL_STATES` re-export.
- No other references anywhere (no test, example, or doc touched it directly).

`global_state` call sites, and whether they relied on process-wide sharing:

| Site | Uses `id=`? | Relied on cross-session sharing? | Action |
|---|---|---|---|
| `examples/global_state.py` | yes (`shared_counter(room)`) | **YES** — the example's whole point was "Shared across sessions by id" | Rewritten: both accessors are now per-session; the `id` row is relabelled as per-entity keying *within* a session |
| `packages/pulse-mantine/.../notifications.py` | no | no | none |
| `tutorial/examples/04-todos.py` + `tutorial/README.md` | no | no (README already says "isolate the global state to a given session") | none |
| `docs/.../cookbook/data-queries/query-invalidation.mdx` | no | no | none |
| `docs/.../reference/pulse/hooks.mdx` | documents `id=` as "Shared per user_id" | docs-only | rewritten |
| `skills/pulse/references/state.md` | documents "Share state across sessions or scope by ID" | docs-only | rewritten |
| `skills/pulse/references/context.md` | documents `id=` as "Separate instance per user_id" | docs-only (already session-safe wording) | clarified |
| `packages/pulse/python/tests/test_render_session.py` | no | no — already asserts isolation across sessions | extended with new tests |

Nothing in this repo depended on process-wide state surviving session teardown.
The only true dependency was `examples/global_state.py`, which existed to
demonstrate the behavior being removed.

### Downstream follow-up (not done here — different repo)

Any downstream app calling `accessor(id=...)` expecting cross-user sharing now
gets per-session instances. Grep downstream for `global_state` accessors invoked
with a positional/keyword `id`; the ones that were only keying per entity
(per-row, per-tab, per-record) keep working unchanged.

## Part 2 — `QueryParamSync` moves from `RouteContext` (mount) to `RenderSession`

### Problem

`QueryParamSync` was constructed per `RouteContext`, i.e. per mount. Its
route→state and state→route effects died with the mount, so a `QueryParam` on a
state that outlives a mount (a session-scoped `global_state` used across in-app
navigation) went stale after the first navigation: the URL stopped updating and
back/forward stopped writing into the state.

### Design

1. **One sync per `RenderSession`** (`RenderSession.query_param_sync`), disposed in
   `RenderSession.close()`. `RouteContext.query_param_sync` is gone.

2. **The session tracks the URL, not "the active mount."** New reactive
   `RenderSession.url: SessionUrl` (`{pathname, hash, queryParams}`), a
   `ReactiveDict` updated by `RouteContext.__init__`/`RouteContext.update`.
   Rationale: one `RenderSession` is one browser tab, and a tab has exactly one
   URL. The JS client already derives every mount's `routeInfo` from the same
   `useLocation()`, so every live mount reports the *same* pathname/hash/query —
   there is no such thing as per-mount disagreement about the URL, only
   per-mount `pathParams`/`catchall` (which query-param sync doesn't use).
   Tracking a URL avoids inventing an "active mount" concept and needing a
   tie-break between the layout mount and the leaf mount.

   *Alternative considered:* a `Signal[RouteContext | None]` holding the
   most-recently-attached mount's route context, with the sync reading through
   it. Rejected: it needs an arbitrary winner when layout + leaf mounts co-exist,
   it thrashes the effect on every mount swap, and it re-introduces exactly the
   mount coupling this change removes.

3. **`navigate_to` attribution.** The sync is no longer route-bound, so it emits
   `sourcePath` (the pathname it serialized against) and *no*
   `sourceRoutePath`/`sourceMountId`. Both `RenderSession.send()` and the JS
   client already have a branch for "sourcePath only": drop the navigation unless
   *some* live view is at that pathname. That is exactly the right staleness
   guard for a session-scoped binding — "is the URL I computed from still the
   current URL", instead of "is mount X still alive". A test asserting
   `sourceRoutePath == "/"` was updated accordingly.

4. **Duplicate param names in one session: displace, don't error (mostly).**
   `_bindings` is now `dict[param, list[binding]]` used as a LIFO stack; the last
   registration owns the URL. Registering a param that is already bound *from the
   same route path* still raises `ValueError` (this is the original guard: two
   states on one page fighting over `?q=`). Registering from a *different* route
   path takes over the param, and disposal restores the previous binding.

   Why not a hard session-wide error (the option the brief called acceptable):
   during client-side navigation React Router loads the new route — which POSTs
   `/prerender`, creating the new mount and its states — *while the old route is
   still mounted*. Two routes that each own a `QueryParam[str] q` (two search
   pages, a shared `FiltersState` class) would collide on every navigation and
   500. Transient overlap is structural, not a user bug, so it must not raise.

   URL→state is applied to *every* binding of a param (a displaced state that is
   still mounted stays consistent with the URL); state→URL only reads the active
   (last) binding, so exactly one state owns the URL at a time. Disposing the
   active binding restores the previous one for URL→state but deliberately emits
   no navigation — teardown should not push URL changes at the client.

5. **Ordering / who wins on navigation.** Unchanged semantics: the URL is the
   source of truth. `_sync_to_route` reads the URL under `Untrack()`, so it
   depends only on binding signals; a URL change therefore triggers only
   route→state, which then re-runs state→URL and finds nothing to write. Navigating
   to a route whose URL lacks the param resets the state to its default — same as
   a back/forward to such a URL, and the same rule as "missing param → default"
   at load. The alternative (state wins, param gets pushed onto the new URL)
   would resurrect params on unrelated pages and fight the browser.

6. **Render-context requirement kept, route requirement dropped.**
   `QueryParamProperty.hydrate`/`initialize` require `ctx.render`; they read the
   session URL instead of `ctx.route`. A state created in a render or callback
   context always has both, but a session-scoped state constructed from a
   non-route context (e.g. a background task holding the render session) is now
   coherent rather than a crash.

### Preserved behavior (covered by the existing suite, all still green)

URL→state on load / back-forward / manual edit; missing param → default; parse
errors raise naming the param; state→URL via `replace` navigation; default and
`None` values omitted; unrelated query params and the hash preserved; list
escaping; naive-datetime warning.

Also checked end-to-end in a browser against `examples/query_param.py` (the
`navigate_to` payload changed, so the client path was worth exercising):
clicking "Next page" rewrote the URL to `?page=2`; loading
`?page=5&tags=alpha,beta&other=keepme` hydrated the state; a further state change
kept `other=keepme`; and Back moved the URL *and* the state to the previous
entry.

## Follow-ups (deliberately not done here)

- Downstream stoneware `rock_detail`: `active_batch` can now drop its
  bridging effect and host the `QueryParam` directly on the session-scoped
  `global_state`. Not touched — different repo.
- `examples/global_state.py` no longer demonstrates multiplayer. If cross-user
  sharing returns, it needs its own named primitive (e.g. `ps.shared_state`) with
  an explicit lifetime/eviction story, not `global_state(id=...)`.
- `RenderSession.prerender(paths)` with `route_info=None` falls back to each
  route's `default_route_info()`, so a multi-path prerender without an explicit
  `routeInfo` sets the session URL from the last path in the list. Only reachable
  in tests and non-browser callers today (the real client always sends
  `routeInfo`), but worth tightening if that ever changes.
