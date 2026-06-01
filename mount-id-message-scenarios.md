# View ID Routing — Revised Design (v4)

## Goals

1. Make `view_id` the **single, internal identity** for every route view across server state and the websocket wire.
2. Keep **path** as the user-facing concept: middleware, `navigate_to` destinations, `RouteInfo`, `ctx.route.route_path`, `ctx.source_path`, error reporting surfaces, debugging tools. Paths are how humans and app code talk about views; view IDs are how the framework dispatches.
3. Support **multiple concurrent pending views per path** so racing prerenders and rapid same-pattern navigations never corrupt state or trigger spurious reloads.
4. Collapse validation to **one map lookup** (`views[view_id]`) on both ends of the wire.

## Non-goals

- Changing how apps register routes, render components, or write callbacks. The view_id refactor is invisible to ordinary route/component/callback code.
- Middleware signatures are explicitly in scope for this refactor: they move to context dataclasses so view-aware dispatch is not spread across ad-hoc kwargs.
- Changing the HTTP prerender request/response shape (still path-keyed — the client asks for paths, the server responds with `{vdom, viewId}` per path).
- Changing the meaning of `navigate_to.path` (still the destination URL).
- Changing the reactive system. Dirty-effect optimization is future work unless this refactor exposes a blocker.

---

## Terminology

The current codebase overloads "path". The plan uses three distinct terms throughout:

- **`route_path`** — the route *pattern* (e.g. `/items/:id`). The unique key in `app.routes` and the key used by `PulseView path` and `#pathToViewId`. This is what we mean by "path" in `views[view_id].route_path`, `active_by_path`, and `pending_by_path`.
- **`pathname`** — the live URL pathname (e.g. `/items/42`). Lives on `RouteInfo`/`ctx.route.pathname`. Never used as a routing key.
- **`destination_path`** — the URL a `navigate_to` is pointing at. Distinct from both above; just a string.

When the plan says "path" without qualification, read `route_path`.

---

## Server data model

Rename `RenderSession.routes` (today the `RouteTree`) to `RenderSession.route_tree` to free the `routes` name for something else — but we'll go further and name the view map explicitly to avoid confusion:

```py
class RenderSession:
    route_tree: RouteTree                       # renamed from `routes`; matching engine
    views: dict[str, RouteView]            # view_id -> instance (every alive view)
    active_by_path: dict[str, str]              # route_path -> active view_id  (1:1)
    pending_by_path: dict[str, set[str]]        # route_path -> set of pending view_ids  (1:N)
    tombstones: collections.OrderedDict[str, ViewTombstone]   # dev-mode only; bounded LRU
```

`RouteSlot` is deleted. `RouteView` keeps its `view_id`, `route_path`, `state`, `route` (RouteContext), `effect`, `queue`, `queue_timeout`, etc.

### State machine

Three states: `pending → active → closed`. No `idle`.

- The only places `idle` mattered in the old code were (a) "pending after prerender timeout — keep around for late attach" and (b) "active whose connection dropped — pause its effect". Both collapse into "pending with a timeout that disposes on expiry."
- Removing `idle` simplifies the state machine. The `effect.pause()` behavior previously tied to `idle` is preserved by an explicit rule (see below).

The `state` field on `RouteView` stays for assertion/debugging, but the source of truth for "which view is current for route_path P" is `active_by_path[P]`, and "which views are awaiting attach for P" is `pending_by_path[P]`.

### Data-level invariants

| Invariant | Rule |
|---|---|
| **Membership** | `view_id in views` ⇔ the view is alive (pending or active). |
| **Single active per path** | `route_path in active_by_path` ⇔ `views[active_by_path[route_path]].state == "active"`. |
| **Pending set membership** | `view_id in pending_by_path[route_path]` ⇔ `views[view_id].state == "pending"`. |
| **Exactly one index** | A view in `views` is in exactly one of: `active_by_path[its route_path]` (as the value) OR `pending_by_path[its route_path]`. Never both, never neither. |
| **Disposal is index-first** | `_dispose_view(view, reason)` removes the view from `views` and from both indexes *first*, cancels pending timers, sets `state = "closed"`, then cleanup runs. Contains no `await`. |
| **Two-guard staleness check** | Stale view-scoped dispatch is detected via *both* `views.get(view_id) is None` (for new resolutions) *and* `view.state == "closed"` (for captured `view` references in effects, hook cleanups, or async callbacks). Navigation from a stale source is dropped/logged; async callbacks otherwise continue running. |
| **State transitions go through one function** | `_set_state(view, new_state)` is the only mutator of `state` + the indexes. No ad-hoc mutation. `_promote`, `_dispose_view`, disconnect handling, and StrictMode handling orchestrate lifecycle work but never edit `active_by_path` / `pending_by_path` directly. |
| **Effects pause on active→pending** | Whenever a view transitions from `active` to `pending` (disconnect, dev-StrictMode detach), its effect is paused via `effect.pause()`. The effect resumes on `_promote`. Without this, a long disconnect would let queued messages grow unboundedly. Any dirty-effect optimization is future work; do not change the reactive system for this refactor unless it becomes a blocker. |
| **Promotion runs outside the reactive batch** | `_promote(view_id)` is invoked only from message handlers and timer callbacks, never from inside `flush_effects()`. `_promote` and `_dispose_view` assert they are not running inside reactive batch flush. Reactive batch flush (`reactive.py:951-973`) iterates an enqueued effect list; disposing a sibling's effect during that iteration would crash. |

### Lifecycle transitions

**`pending → active` (promotion)**, triggered by `attach(view_id)` or by a callback on a pending view:

```py
def _promote(view_id, reason):
    view = views[view_id]
    rp = view.route_path
    # 1. Dispose every sibling pending — synchronous, no await
    for sibling_id in list(pending_by_path.get(rp, ())):
        if sibling_id != view_id:
            _dispose_view(views[sibling_id], reason="superseded")
    # 2. Dispose the previous active (if any) — synchronous
    prev_active_id = active_by_path.get(rp)
    if prev_active_id and prev_active_id != view_id:
        _dispose_view(views[prev_active_id], reason="replaced")
    # 3. Move this view from pending to active.
    #    _set_state owns all index mutation.
    _set_state(view, "active")
    view.effect.resume()   # safe no-op if already running
    # 4. Flush queued messages
    view.flush_queue(send_message)
```

`_set_state(view, new_state)` removes the view from the old state's index, updates `view.state`, then inserts it into the new state's index. For `"active"`, it asserts no different active view exists for the same `route_path`; callers must dispose/close the previous active first. For `"closed"`, it also removes the view from `views`. This keeps every transition observable as one consistent operation and gives tests a single invariant checkpoint.

**`pending → closed` (disposal)**: timeout fires, or `detach`, or a sibling promotes, or session closes. Always carries an explicit `reason` string (`"timeout"`, `"detached"`, `"superseded"`, `"replaced"`, `"session_close"`, `"disconnect_timeout"`, `"strict_mode_timeout"`).

`_dispose_view(view, reason)` is idempotent: if `view.view_id not in views` or `view.state == "closed"`, it returns. Otherwise it records the tombstone, cancels the pending timeout, calls `_set_state(view, "closed")`, then unregisters forms and route-bound channels/refs for the view, unmounts the tree, and disposes the effect. Cleanup is best-effort and exception-safe: catch/report each cleanup failure and continue to the next cleanup step. It contains no `await`.

**Callback on a pending view** must follow this order:

1. **Look up:** `view = views[msg.viewId]`. If `None` → drop.
2. **Promote if pending:** if `view.state == "pending"`, run `_promote(view.view_id, reason="callback_promoted")` synchronously. This disposes siblings, disposes the previous active for this `route_path`, marks the view active, resumes its effect, and flushes its queue (so the client applies any pending `vdom_update` ops *before* it sees the callback's side effects).
3. **Execute the callback** under a `PulseContext` whose `view` is the now-active view.

The promote-then-execute order matters: running the callback first would (a) leave the previous active alive while the callback writes signals that fire effects on *both* views, producing redundant `vdom_update`s the client must drop as stale; (b) expose a still-pending view as `ctx.view`, which is surprising to handlers; (c) cause any `ps.redirect(...)` inside the callback to enqueue its `navigate_to` (sourceViewId=this) until promotion fires, instead of sending immediately.

Promotion flushes queued render/error messages before executing the callback, but queued `navigate_to` messages from the pending phase are dropped with a dev warning. A user action on the pending view wins over stale pending navigation. `flush_queue` therefore means: send queued VDOM/error/API/JS/channel messages in order, skip route-bound `navigate_to`, and clear the queue. It also cancels the pending timeout.

**`active → pending` (disconnect)**: on socket disconnect, every active view converts to pending with `disconnect_queue_timeout`, AND its effect is paused. **Pre-existing pendings also get their timeout extended to `max(remaining, disconnect_queue_timeout)`** — cancel the existing timeout handle, then schedule the replacement timeout. The client's `#views` already holds these view IDs and will replay attach on reconnect, so they have a real expectation. Pre-existing pendings' effects are already not flushing aggressively (they're lazy until a state-change triggers them), but to be safe, pause them too if they had been running since prerender.

Pending timeout callbacks are generation-checked: the callback only disposes when `view.state == "pending"` and the firing timer handle/generation is still the view's current `queue_timeout`. Promotion and disposal cancel the current timeout and clear the handle.

**`active → closed`**: `detach` matching view_id, or promotion of a different pending, or session close.

### Tombstones (dev-mode observability)

`_dispose_view(view, reason)` inserts a tombstone:

```py
class ViewTombstone:
    view_id: str
    route_path: str
    pathname: str | None
    disposed_at: float
    reason: str    # passed by the disposer; never inferred
```

`tombstones` is a bounded LRU (last 100 entries per session). A tombstone is a short-lived dev/debug record explaining why a view ID that used to exist was disposed. Whenever a wire message references a `view_id` not in `views`, the dispatcher logs `views.get(view_id) is None; tombstone={tombstones.get(view_id)}`. Production builds compile this to a no-op.

**Scope:** tombstones are server-side only. Client-side stale drops (which today are silent) remain silent — they can be added later if observability demand emerges. The plan does not require client tombstones.

---

## Wire protocol

### Client → Server

Client messages are explicitly one of three scopes:

1. **View-scoped** — produced from route-owned UI and must include `viewId`.
2. **Session-scoped** — produced outside any route view and must be globally/session-defined by message type or carry an explicit `scope: "session"` when ambiguity is possible.
3. **Correlation-only** — responses such as `api_result` / `js_result`; they include `id`, and the server validates the id against its stored owner metadata.

As a rule, tag client messages with `viewId` whenever the client can know the owning view. Missing `viewId` is never used to guess "current route"; it means "this message is session/global or invalid for this surface."

`viewId` is authority only after server validation. It is server-minted, unguessable, scoped to one `RenderSession`, and valid only for the owning socket/render session. The dispatcher must reject/drop any `viewId` that is not present in `render.views` for that render session; a syntactically valid ID from another session is stale/invalid.

Every view-scoped client message carries `viewId` and nothing else for route dispatch:

| Type | Fields |
|---|---|
| `attach` | `viewId`, `routeInfo` |
| `update` | `viewId`, `routeInfo` |
| `detach` | `viewId` |
| `callback` | `viewId`, `callback`, `args` |
| `api_result` | `id`, `viewId?`, `ok`, `status`, `headers`, `body` (route-bound responses must echo `viewId`; session responses omit it) |
| `js_result` | `id`, `viewId?`, `result`, `error` (route-bound responses must echo `viewId`; session responses omit it) |
| `channel_message` (route-bound) | `channel`, **`viewId`**, `event` or `responseTo`, `payload`, `requestId?`, `error?` |
| `channel_message` (session-bound) | `channel`, `scope: "session"`, `event` or `responseTo`, `payload`, `requestId?`, `error?` |

**Channel messages must carry `viewId` for route-bound channels.** The client's `Channel` object stores the view_id it was bound to at construction; outbound channel messages from a route-bound channel include that `viewId`. Without this, the server cannot resolve which `(view_id, channel_id)` internal-key entry receives the message when concurrent pendings own the same channel name.

Channel scope is validated against the server's registered channel, not inferred independently on each side:

- `viewId` present: resolve `(viewId, channelId)`. If only a session-bound `channelId` exists, reject/log a scope mismatch.
- `viewId` absent: resolve the session-bound `channelId` only. If only route-bound channels exist for that raw id, reject/log missing `viewId`.
- A raw `channelId` may not be registered as both session-bound and route-bound in one render session unless the route-bound wire always carries `viewId` and the session-bound wire is explicitly session-scoped. Prefer failing on ambiguity during registration.

`ClientUpdateMessage` changes shape: `{type: "update", path, routeInfo}` → `{type: "update", viewId, routeInfo}`. Tests and `PulseView`'s route-sync effect both update to send the effect-captured `viewId` instead of `path`.

### Server → Client

View-scoped (carry `viewId`):

| Type | Fields |
|---|---|
| `vdom_update` | `viewId`, `ops` |
| `vdom_init` | (HTTP prerender only — never on the wire) `viewId`, `vdom` |
| `server_error` (view-bound) | `viewId`, `error` |
| `js_exec` (route-bound) | `viewId`, `id`, `expr` |
| `api_call` (route-bound) | `viewId`, `id`, `url`, `method`, `headers`, `body`, `credentials` |
| `navigate_to` (route-bound) | `path` (destination URL), `replace`, `hard`, `sourceViewId` |
| `channel_message` (route-bound) | `channel`, `viewId`, `event`/`responseTo`, `payload`, ... |

Global (no scoping field):

| Type | Fields |
|---|---|
| `reload` | — |
| `server_error` (session-level) | `error` |
| `js_exec` (session-level) | `id`, `expr` |
| `api_call` (session-level) | `id`, `url`, ... |
| `navigate_to` (forced) | `path`, `replace`, `hard` |
| `channel_message` (session-level) | `channel`, `scope: "session"`, `event`/`responseTo`, `payload`, ... |

`navigate_to` drops `sourceRoutePath` and `sourcePath` from the wire. `sourceViewId` is sufficient; the server derives both from `views[sourceViewId]` for logging, and the client validates by view_id.

### Middleware signatures — switch to context objects

Today's middleware methods have inconsistent, positional-ish signatures:

```py
prerender(payload, request, session, next)
connect(request, session, next)
message(data, session, next)
channel(channel_id, event, payload, request_id, session, next)
```

Adding view-related kwargs (`route_path`, `view_id`, `route_info`) to each signature would (a) be inconsistent across methods and (b) break user-written middleware overrides — and we don't care about backward compat in this refactor, so we take the chance to clean this up properly.

**New shape:** every middleware method receives a single context dataclass plus `next`:

```py
@dataclass(frozen=True)
class PrerenderMiddlewareContext:
    payload: PrerenderPayload
    request: PulseRequest
    session: SessionData

@dataclass(frozen=True)
class ConnectMiddlewareContext:
    request: PulseRequest
    session: SessionData

@dataclass(frozen=True)
class MessageMiddlewareContext:
    msg: ClientMessage
    view_id: str | None          # None for global messages
    route_path: str | None        # derived from view; None if view unknown
    route_info: RouteInfo | None  # derived from view
    session: SessionData

@dataclass(frozen=True)
class ChannelMiddlewareContext:
    channel_id: str               # raw, user-facing id (never the internal key)
    event: str
    payload: Any
    request_id: str | None
    view_id: str | None          # None for session-bound channels
    route_path: str | None
    route_info: RouteInfo | None
    session: SessionData

class PulseMiddleware:
    async def prerender(self, ctx: PrerenderMiddlewareContext, next): ...
    async def connect(self, ctx: ConnectMiddlewareContext, next): ...
    async def message(self, ctx: MessageMiddlewareContext, next): ...
    async def channel(self, ctx: ChannelMiddlewareContext, next): ...
```

**Dispatcher normalization.** `_handle_pulse_message` and `_handle_channel_message` in `app.py` resolve the view once per message and build the context.

Unknown scoped views are handled by the framework before user middleware runs:

- `attach` with unknown `viewId` sends `reload`.
- Other view-scoped messages with unknown `viewId` are tombstone-logged in dev and dropped.
- Session/global messages continue into middleware with `view_id=None`.

After that framework gate, middleware context construction is:

```python
async def _handle_pulse_message(self, render, session, msg):
    view_id = msg.get("viewId")
    view = render.views.get(view_id) if view_id else None
    ctx = MessageMiddlewareContext(
        msg=msg,
        view_id=view_id,
        route_path=view.route_path if view else None,
        route_info=view.route.info if view else None,
        session=session.data,
    )
    await self.middleware.message(ctx, _next)
```

Middleware may `await`, so `_next` revalidates the target view immediately before dispatching the message. If `viewId` no longer resolves to the same live view, `_next` tombstone-logs and drops instead of executing stale callback/update/detach/channel work.

**Channel responses** (with `responseTo`) still bypass channel middleware — responses are correlated by request id, not authorized by user middleware. They are still framework-validated: `(viewId | None, channel, responseTo)` must match `PendingRequest.channel_internal_key`; request id alone is not sufficient.

**Tradeoffs.** Migrating user-written middleware is a one-line signature change. Extensibility wins: new fields land as new attributes on the context, not new positional/keyword args spreading across every override. Self-documenting via the dataclass shape. View-aware authorization rules ("only allow channel X on route Y") become natural to write.

**`prerender` and `connect` middleware are pre-view** — they don't carry `view_id`/`route_path`/`route_info`. Their context objects exist just for signature consistency.

---

## Client data model

```ts
class PulseSocketIOClient {
    #views: Map<string, ClientView>;        // KEY: viewId
    #pathToViewId: Map<string, string>;     // route_path -> active viewId
}

interface ClientView {
    viewId: string;
    routePath: string;
    routeInfo: RouteInfo;
    onUpdate, onJsExec, onServerError;
}
```

### Client invariants

| Invariant | Rule |
|---|---|
| View lookup is one map get | `#views.has(viewId)` is the only "is this view current?" check. |
| **Attach evicts previous view for same routePath** | `attach({viewId, routePath, routeInfo})`: if `#pathToViewId[routePath]` already points to a *different* viewId, **delete that entry from `#views`** (it's the old same-pattern view that will never receive its own `detach`). Then add the new entry to `#views`, set `#pathToViewId[routePath] = viewId`, and send the wire `attach`. |
| **Stored routeInfo stays fresh** | `update({viewId, routeInfo})` updates `#views[viewId].routeInfo` before sending the wire update. Reconnect replay uses this stored value, so queued `update` messages can be skipped safely. |
| `detach(viewId)` write guard | Removes `#views[viewId]`. Only clears `#pathToViewId[routePath]` if it still equals `viewId`. Required when React commits old cleanup after new setup. |
| `#views` persistence | `#views` persists across socket-level disconnect/reconnect. Only explicit `client.disconnect()` (PulseProvider unmount / StrictMode) clears it. |

The "attach evicts" rule is the equivalent of today's path-keyed `#activeViews` replace-on-attach behavior, ported to the view-id model. Without it, same-pattern navigation accumulates stale views in `#views` indefinitely (because same-pattern nav never sends `detach`, by the "Same-pattern nav never sends detach" invariant).

### Reconnect replay

On `socket.on("connect")`, replay an `attach` for every entry in `#views` (iterate by viewId, not path). Skip queued `attach`/`update` messages from `#messageQueue` (they're superseded by the replay).

### PulseView lifecycle

Three effects, semantics unchanged:

1. **View-sync** (`useLayoutEffect`, deps `[client, routePath, viewId, renderer]`) — `client.attach({viewId, routePath, routeInfo})`, `setTree(renderer.init(initialView))`.
2. **Lifecycle** (`useEffect`, deps `[client, routePath, viewId]`) — cleanup sends `detach(viewId)` for the view captured by that effect. Do not read a mutable `latestViewId` ref in cleanup.
3. **Route-sync** (`useEffect`, deps `[client, viewId, routeInfo]`) — `client.update({viewId, routeInfo})` for the view captured by that effect. Do not read a mutable `latestViewId` ref.

**Load-bearing assumption:** every `PulseView` in the rendered tree (layout + page + nested layouts) gets its own `viewId` from the HTTP prerender response. The HTTP prerender request must include the full chain of route patterns the React tree will render.

### HTTP prerender route chain

The generated React Router loader derives the chain from `matchRoutes(rrPulseRouteTree, url.pathname)` and sends route patterns in render order:

```ts
{
    paths: ["/<layout>", "/dashboard/<layout>", "/dashboard/:id"],
    routeInfo
}
```

The server responds with the same path keys:

```ts
{
    views: {
        "/<layout>": { viewId, vdom },
        "/dashboard/<layout>": { viewId, vdom },
        "/dashboard/:id": { viewId, vdom },
    },
    directives
}
```

If any path in the requested chain redirects or returns not-found, the whole prerender batch returns that redirect/not-found and disposes every view created by the batch. If a requested path is not in the server route tree, prerender fails as not-found/reload rather than creating a partial chain.

---

## Channels — view-namespaced

`ChannelsManager.create(identifier)` today rejects duplicate channel IDs session-wide (`channel.py:93-95`). With concurrent pendings on the same route, both renders call `ps.channel("chat")` and the second raises. **Fix:** scope channel-ID uniqueness by `(view_id, channel_id)` for route-bound channels.

### Internal-key boundary (server)

The principle: **wire and user-facing APIs use raw `channel_id`; everything inside `ChannelsManager` uses the internal key.** Conversion happens at the wire boundary (incoming: derive internal from raw + `viewId`; outgoing: emit raw + `viewId`).

```py
class ChannelsManager:
    _channels: dict[ChannelKey, Channel]                   # internal_key -> Channel
    _channels_by_view: dict[str, set[ChannelKey]]         # view_id -> {internal_key, ...}
    pending_requests: dict[str, PendingRequest]            # request_id -> PendingRequest

ChannelKey = tuple[str | None, str]  # (view_id, raw channel_id); None means session-bound

@dataclass
class PendingRequest:
    future: Future
    channel_internal_key: ChannelKey   # NOT the raw channel_id — internal key
                                       # so cancellation across views doesn't cross-fire

def _internal_key(channel_id: str, view_id: str | None) -> ChannelKey:
    return (view_id, channel_id)
```

Where each existing method/field falls on the boundary:

| Surface | Key type | Notes |
|---|---|---|
| `_channels` keys | **internal** | `(view_id, channel_id)` for route-bound; `(None, channel_id)` for session-bound |
| `_channels_by_view[view_id]` set values | **internal** | for `remove_route` |
| `PendingRequest.channel_internal_key` | **internal** | renamed from `channel_id`; prevents cross-view cancellation of pending requests sharing a raw id |
| `_cancel_pending_for_channel(internal_key)` | **internal** | iterates and matches on `channel_internal_key` |
| `release_channel(channel_id, view_id)` | accepts **raw + view_id** | resolves internal_key internally |
| `_send_error_response(channel_id, request_id, error)` | resolves internal_key via `pending_requests[request_id].channel_internal_key` | request_id is sufficient to find the right channel |
| `send_to_client(channel, msg)` | stamps **raw** `msg["channel"] = channel.id` + `msg["viewId"]` for route-bound | wire is raw |
| `__close__` notification wire fields | **raw** `channel` + `viewId` for route-bound | client resolves to its own internal key |
| `ps.channel(channel_id)` (user-facing) | accepts **raw**; derives internal_key from `ctx.view.view_id` | `Channel.id` field exposes raw |

`remove_view(view_id)` closes every internal key in `_channels_by_view[view_id]`. The path-keyed `_channels_by_route` index is dropped.

Use tuple keys internally. Avoid string-concatenated internal keys; user channel IDs may contain separators.

### Internal-key boundary (client)

The JS client mirrors the same split:

| Surface | Key type | Notes |
|---|---|---|
| `#channelsByView: Map<string \| null, Map<string, ChannelBridge>>` | **internal** | outer key is `viewId` or `null` for session-bound; inner key is raw `channelId`. Do not use `Map<object, ...>` because object keys compare by identity. |
| `ChannelBridge.id` (and user-facing object) | **raw** | what the user sees |
| `acquireChannel(channelId, viewId?)` | **raw + viewId** | resolves internal_key; `viewId` from React context |
| Outbound wire messages | **raw** `channel` + `viewId` for route-bound | stamps viewId from bridge's owning view |
| Inbound dispatch (`#routeChannelMessage`) | resolves internal_key from message's `channel` + `viewId` | one map lookup |

### React `PulseViewContext`

Today's `usePulseChannel(channelId)` has no view context — it just talks to the singleton client. To stamp `viewId` on outbound route-bound channel messages, the client needs to know which view the hook is running under.

Add a React context provided by every `PulseView`:

```tsx
interface PulseViewContextValue {
    viewId: string;
    routePath: string;
}
const PulseViewContext = createContext<PulseViewContextValue | null>(null);

// Inside PulseView's render:
<PulseViewContext.Provider value={{ viewId, routePath }}>
    {tree}
</PulseViewContext.Provider>
```

`usePulseChannel(channelId)` reads `PulseViewContext`:

```tsx
export function usePulseChannel(channelId: string): PulseChannel {
    const client = usePulseClient();
    const view = useContext(PulseViewContext);  // null if used outside a PulseView (session-scoped)
    return useMemo(
        () => client.acquireChannel(channelId, view?.viewId ?? null),
        [client, channelId, view?.viewId],
    );
}
```

A hook called outside any `PulseView` (e.g. in a global session-level component) gets `null` and falls through to session-bound channel semantics. Hooks called inside a `PulseView` get the view's identity.

---

## Forms — disposed with view

`FormRegistration` keeps `view_id`. `handle_submit` (`forms.py:139-208`):

```py
view = render.views.get(registration.view_id)
if view is None:
    raise HTTPException(410)
raw_form = await request.form()
view = render.views.get(registration.view_id)
if view is None or view.state == "closed":
    raise HTTPException(410)
if view.state == "pending":
    if render.send_message is None:
        raise HTTPException(409, detail="View is not attached")
    render._promote(view.view_id, reason="form_promoted")
elif view.state != "active":
    raise HTTPException(410)
```

One map lookup; no path involvement. Because form parsing can await, the handler revalidates `views[view_id] is view` after reading the request body and before promotion/handler execution. A submit against a pending view is treated like a callback only if the websocket sender is available: promote first, flush queued updates, then run the form handler under that view. If the view is pending but no websocket sender exists, return `409` (or equivalent reload-required response) rather than promoting an unattached view.

**New invariant:** form registrations are disposed when their owning view is disposed. `_dispose_view(view, reason)` calls `render.forms.unregister_by_view(view.view_id)`. This is a safety net; the existing `FormStorage` hook lifecycle already handles the common case (forms are part of the view's tree, unmounted together).

---

## Refs — view-namespaced route channels

Refs are route-bound channels and must follow the same view namespace rules as user channels.

- Server ref channels are keyed by `(view_id, channel_id)`, not by `route_path`.
- Client ref callbacks use the owning `PulseView` view id and stamp `viewId` on `ref:mounted`, `ref:unmounted`, and ref request/response messages.
- `_dispose_view` closes all ref channels owned by the view.
- Server validates ref scope the same way as route-bound channels: present `viewId` must match a registered route-bound ref channel; missing `viewId` is session/global only.

Without this, two concurrent pending renders for the same route can share the same route ref channel and deliver ref mount/unmount or request messages to the wrong `RefHandle`.

---

## Client request futures — owner validated

`api_result` and `js_result` remain correlated by `id` on the wire, but server-side pending request tables store the owner view:

```py
@dataclass
class PendingClientRequest:
    future: Future
    owner_view_id: str | None
```

When a route-bound `api_call` or `js_exec` is sent, `owner_view_id` is set to the source view id. `_dispose_view` does **not** cancel arbitrary async callback work just because the source view closed. When a result arrives, the server resolves the future by correlation id; route-bound results must include `viewId` and it must match `owner_view_id`. Mismatch rejects the stored future with a stale-view error and logs; it does not silently drop and wait for timeout. If the client cannot execute the request because the view is stale, it sends a stale/error result so the server future does not hang. If server code attempts a new route-bound API/JS request from an already-closed source view, resolve/reject immediately with a stale-view error instead of sending to the client.

This lets async callbacks proceed after their source view closes. The stale-source rule applies specifically to navigation calls from that callback.

---

## Query param sync — drops sourceRoutePath/sourcePath

`QueryParamSync._sync_to_route` (`state/query_param.py:486-543`) currently emits `navigate_to` with `sourceRoutePath`, `sourcePath`, `sourceViewId`. The wire change drops the first two:

```python
message = ServerNavigateToMessage(
    type="navigate_to",
    path=path,                      # destination URL
    replace=True,
    hard=False,
    sourceViewId=source_view_id,  # required when route-bound
)
```

Server's `send()` resolves `sourceViewId → views[id].route_path` for validation.

Equivalent changes in `hooks/runtime.py` (lines 262+) where `navigate_to`-style messages are emitted from the runtime hooks.

Stale route-bound navigation is a no-op: if `sourceViewId` no longer resolves on the server or no longer exists in the client's `#views`, drop the navigation and emit a dev warning/tombstone log. Forced/global `navigate_to` has no `sourceViewId` and always applies.

`sourceViewId` is a source-liveness check, not a full route freshness epoch. If a still-alive layout intentionally emits delayed navigation after its `routeInfo` changes, the navigation is allowed. Add a route epoch later only if this becomes a real app-level bug.

---

## HTTP prerender / vdom baseline coherence

The HTTP prerender response carries the initial `{viewId, vdom}` for each path. The client renders that vdom and treats it as the **baseline** for all subsequent `vdom_update` ops on the same view.

**Invariant:** `tree.render()` (first call, during prerender) and `tree.rerender()` (subsequent, during effect flushes) share a baseline. Ops queued during pending state are coherent diffs from the prerendered vdom, applied in order on promotion. The server never sends a `vdom_init` over the websocket; the client never resets its baseline mid-view.

If `attach(viewId)` arrives after the pending view timed out and was disposed, the server sends `reload`. This is intentional for v1; per-view re-prerender over the websocket is future work.

---

## Dev StrictMode handling

React StrictMode fires `attach → detach → attach` synthetically on first view in development. The current code preserves the view for a short `dev_strict_mode_detach_timeout` window (`render_session.py:686-694`) by keeping it in `slot.active` so that path-keyed channel/form lookups still find it during the gap.

In the new model, this special case is no longer needed:

- Channels resolve by `(view_id, channel_id)` internal key. The replayed `attach` reuses the same `viewId`, so channels keep working as long as the view exists in `views`.
- Forms resolve by `views.get(view_id)`. Same property.
- No incoming wire message during the gap is path-keyed; everything is view-keyed.

So **StrictMode detach is just a normal `_dispose_view` with a delay**:

- On detach in dev mode, instead of disposing immediately, move the view from `active_by_path` into `pending_by_path` with `state="pending"`, pause its effect, and start a `dev_strict_mode_detach_timeout` with `reason="strict_mode_timeout"`.
- If the replayed `attach` arrives within the window, `_promote` finds it in `pending_by_path[route_path]` (single-element set; no siblings to dispose), resumes the effect, marks it active again. Normal promotion path.
- If the timer expires first, dispose normally with `reason="strict_mode_timeout"`.

The "exactly one index" invariant holds throughout — no exception needed. Channels and forms don't observe the view disappearing from `active_by_path` during the gap because their lookups never touch that index in the new model.

Client-side StrictMode still runs descendant effect cleanups. Route-bound channels and refs therefore also need client-side replay tolerance:

- `usePulseChannel` release sends `__close__` with `viewId`; the server delays route-bound channel disposal for the same StrictMode grace window when the owning view is also pending for StrictMode.
- Reacquiring the same `(viewId, channelId)` within the grace window cancels that delayed close and reuses the bridge/channel.
- Ref channel disposal follows the same delayed-close rule.
- Track delayed closes explicitly: `pending_channel_closes: dict[ChannelKey, TimerHandle]` and equivalent ref-channel close timers. `_dispose_view` for a real close cancels these timers and closes owned channels/refs immediately.

This keeps the server view grace and client hook cleanup semantics aligned.

---

## Scenarios matrix (revised)

| Scenario | Wire message | Direction | Key | Server behavior |
|---|---|---|---|---|
| Initial HTTP prerender returns VDOM | `vdom_init` in HTTP body | server → client (HTTP) | `viewId` | Creates `RouteView` in `views`, adds to `pending_by_path[route_path]`, schedules `prerender_queue_timeout` |
| Initial HTTP prerender redirects/notFound | HTTP body | server → client (HTTP) | — | Disposes every view created by that prerender batch |
| Client attaches initial prerendered view | `attach` | client → server | `viewId` | `views.get(viewId)` → pending → `_promote`; if missing → `reload` |
| Same-pattern nav creates new pending | `attach` (new id) | client → server | `viewId` | `_promote` disposes previous active + any sibling pendings. **Client also evicts previous viewId from `#views` when adding new entry for same routePath.** |
| Concurrent prerenders for same path | n/a (server-internal) | — | — | Each adds a new entry to `pending_by_path[route_path]`; siblings coexist until one is attached |
| Parent layout sees child route change | `update` | client → server | `viewId` of layout | `views[viewId].update_route(routeInfo)` — view-scoped |
| Same view query/hash change | `update` | client → server | `viewId` | Same |
| Client callback from DOM event | `callback` | client → server | `viewId` | `views.get(viewId)`; callback key resolved only in that view's tree; if pending → `_promote` then execute |
| HTTP form submit | form POST | client → server (HTTP) | form registration's `view_id` | `views.get(viewId)`; if pending → `_promote` then execute; if missing/closed → 410 |
| Async callback after detach/remount | side effects | server-internal / server → client | source view id in context | Callback continues. State writes still happen. Navigation from a stale source view is dropped/logged. |
| Active rerender VDOM diff | `vdom_update` | server → client | `viewId` | Delivered if active, queued if pending |
| Pending rerender VDOM diff | `vdom_update` | server → client | `viewId` | Queued; flushed on promotion; dropped if disposed |
| Active rerender redirect | `navigate_to` | server → client | `sourceViewId` | Server and client validate source; stale source drops/logs |
| Forced navigate | `navigate_to` | server → client | — | Global, applied unconditionally |
| Query param sync nav | `navigate_to` | server → client | `sourceViewId` | `ctx.source_view_id` set; route_path derived |
| View-bound server error | `server_error` | server → client | `viewId` | Queued for pending, sent for active |
| Session-level server error | `server_error` | server → client | — | Global |
| Route-bound channel message | `channel_message` | both | `(viewId, channel)` | Resolved to internal key |
| Route-bound ref message | `channel_message` | both | `(viewId, ref channel)` | Resolved like a route-bound channel |
| Session-level channel message | `channel_message` | both | `channel` | Resolved by channel id alone |
| Reload request | `reload` | server → client | — | Global |
| Detach route | `detach` | client → server | `viewId` | `views.pop(viewId)`; clean indexes; dispose; tombstone |
| Reconnect attach replay | `attach` per view | client → server | `viewId` | Each replays; promote if pending, no-op if already active, reload if disposed |
| Late attach for superseded/timed-out view | `attach` | client → server | `viewId` | Reload is intentional. Client should suppress stale loader commits where possible, but server treats unknown attach as reload-required. |
| Brand-new render session on reconnect | `attach` | client → server | `viewId` | `views` empty → reload |
| Delayed stale wire message | any view-scoped | server → client | `viewId` | Client: `#views.has` → drop. Server: `views.get → None`; log tombstone; drop |
| Delayed API/JS result | `api_result` / `js_result` | client → server | correlation id | Server resolves by id; optional `viewId` must match stored owner; stale/error results unblock the future |
| StrictMode replay (dev) | `attach → detach → attach` | client → server | `viewId` | First detach moves view to `pending_by_path` with `dev_strict_mode_detach_timeout`; second attach reuses the same viewId and promotes normally |

---

## Core invariants (revised)

| Invariant | Rule |
|---|---|
| **View identity** | Any message originating from a view carries `viewId` (or `sourceViewId` for navigation). |
| **Two-guard staleness** | Server-side, stale messages are dropped via `views.get(view_id) is None` AND `view.state == "closed"` (for captured-reference emissions). Both checks are load-bearing. |
| **One-lookup resolution** | The primary dispatch check is one map get. |
| **Promotion is atomic and synchronous** | `_promote(view_id)` disposes siblings and the previous active in one synchronous block. No `await` mid-promotion. |
| **Promotion runs outside reactive batches** | `_promote` is invoked from message handlers and timer callbacks only; never from inside `flush_effects()`. |
| **`update` is view-scoped and route-validated** | Mutates the named view's `RouteContext` only after validating the incoming `RouteInfo` still matches the view's `route_path` pattern and derived path params/catchall. Invalid updates drop/log. |
| **Path is a derived label** | The wire never uses path as a routing key. Path is read from `views[viewId].route_path` for middleware, logging, observability. |
| **Global messages are explicit** | `reload`, forced `navigate_to`, session-level `channel_message`/`js_exec`/`api_call`, session-level `server_error`. |
| **Stale source navigation means no-op** | `sourceViewId` resolves through `views`; missing → drop/log for route-bound navigation. Async callbacks otherwise continue. |
| **Stale scoped input bypasses user middleware** | Unknown `viewId` is handled by framework dispatch first: `attach` reloads, all other scoped messages tombstone-log/drop. |
| **`vdom_init` is HTTP-only** | Subsequent `vdom_update` ops diff against the HTTP-delivered baseline. |
| **Disposal is index-first** | `_dispose_view(view, reason)` removes from `views` + indexes, sets state=closed, then unmounts tree, then disposes effect. |
| **Effects pause on active→pending** | The disconnect transition pauses the effect; promotion resumes it. |
| **Same-pattern nav never sends `detach`** | Client cleanup only fires on routePath change. Server-side, the new attach's promotion disposes the old active. |
| **Client attach evicts** | Adding a new entry to `#views` for a routePath that already has a different viewId deletes the old entry from `#views`. |
| **Every PulseView has its own view** | Every `PulseView` in the React tree corresponds to a distinct server view with its own `viewId` returned by the HTTP prerender. |
| **Channels scope by view** | Route-bound channels are keyed internally by `(view_id, channel_id)`. |
| **Refs scope by view** | Route-bound ref channels are keyed internally by `(view_id, channel_id)` and use the same stale/drop rules as channels. |
| **Forms dispose with view** | `FormRegistration` lifetime is bounded by the owning view; `_dispose_view` unregisters all forms owned by the view. |
| **Callbacks are view-local** | Callback keys are resolved only in the render tree for the provided `viewId`. A callback key from a sibling/stale view must not execute under another valid view. |
| **Client request futures have owners** | Route-bound API/JS pending futures store `owner_view_id`; late results still unblock callbacks, but mismatched `viewId` results reject/log. |

---

## User-facing surfaces (unchanged)

- **Middleware** (`prerender/connect/message/channel`): receives paths and `RouteInfo`. Message and channel middleware get `path`/`route_path` injected by the dispatcher's normalization step; `None` for global/session messages.
- **`navigate_to(path, ...)`**: destination URL.
- **`RouteInfo`**: path-based.
- **`ctx.route.route_path` / `ctx.source_path`**: path strings.
- **`ctx.source_view_id`**: framework-internal identifier.
- **`@route` decorators, `app.routes`** (path-keyed; the underlying field is renamed `route_tree`).
- **Error UI** (`ServerError`): `phase` + message; `viewId` field is correlation only.
- **Logs**: include `route_path` (from `views[viewId].route_path` or from tombstone) alongside `viewId`.

---

## Migration footprint

### Server (Python)
- `packages/pulse/python/src/pulse/render_session.py` — rename `routes` field to `route_tree`; introduce `views` / `active_by_path` / `pending_by_path`; rewrite `attach` / `update_route` / `detach` / `prerender` / `promote_pending_view` / `dispose_view` / `send`; add `_dispose_view(reason)` everywhere disposal happens; add `effect.pause()` on `active→pending`. Treat `render.routes` as internal; this is an intentional internal breaking change. Rename `RouteInstance` / `RouteMount` aliases to `RouteView` where they are public/exported, or keep compatibility aliases until cleanup.
- `packages/pulse/python/src/pulse/channel.py` — switch `_channels` to internal-key model; add `_channels_by_view`; drop `_channels_by_route`; `remove_view(view_id)` signature change.
- `packages/pulse/python/src/pulse/forms.py` — `handle_submit` uses `views.get(view_id)` and promotes pending views before executing; `FormRegistry.unregister_by_view`; called from `_dispose_view`.
- `packages/pulse/python/src/pulse/refs.py` and route ref-channel creation in `render_session.py` — route-bound ref channels become view-namespaced and are disposed by view.
- `packages/pulse/python/src/pulse/context.py` — rename internal context fields `mount` / `source_mount_id` to `view` / `source_view_id`, or provide temporary aliases during migration.
- `packages/pulse/python/src/pulse/state/query_param.py` — drop `sourceRoutePath`/`sourcePath` from emitted `navigate_to`.
- `packages/pulse/python/src/pulse/hooks/runtime.py` (around line 262) — same: drop `sourceRoutePath`/`sourcePath` from server-emitted `navigate_to`.
- `packages/pulse/python/src/pulse/app.py` — middleware normalization in `_handle_pulse_message` and `_handle_channel_message`; message router updated for view-scoped `update`/`detach`/`callback`.
- `packages/pulse/python/src/pulse/middleware.py` — replace all four middleware-method signatures with context-dataclass arguments (`PrerenderMiddlewareContext`, `ConnectMiddlewareContext`, `MessageMiddlewareContext`, `ChannelMiddlewareContext`).
- `packages/pulse/python/src/pulse/messages.py` — wire type changes: drop `path` from `ClientUpdateMessage`/`ClientDetachMessage`/`ClientCallbackMessage`/view-scoped server messages; add `viewId` to `ClientChannelRequestMessage`/`ClientChannelResponseMessage` (optional, for route-bound); drop `sourceRoutePath`/`sourcePath` from `ServerNavigateToMessage`.

### Client (TypeScript)
- `packages/pulse/js/src/client.tsx` — `#views` keyed by viewId; `#pathToViewId` index; attach-evicts-on-same-routePath behavior; detach write guard; channel internal keying via owning viewId; reconnect replay iterates viewIds.
- `packages/pulse/js/src/channel.ts` — `Channel` stores its bound viewId (route-bound); outbound messages stamp `viewId`; bridges keyed by internal `(viewId, channelId)` for route-bound. `usePulseChannel(channelId)` reads `PulseViewContext` to resolve viewId.
- `packages/pulse/js/src/pulse.tsx` — `client.attach({routePath, viewId, routeInfo})`; `client.update({viewId, routeInfo})`; `client.detach(viewId)`; **new `PulseViewContext` provided by every `PulseView`** so descendant hooks (channels, refs, future view-bound hooks) can stamp the viewId.
- `packages/pulse/js/src/renderer.tsx` — `invokeCallback(viewId, ...)` (drop path); view id is already stamped at render time; callback metadata and stale callback cleanup use `viewId`.
- `packages/pulse/js/src/ref.ts` / renderer ref registry — route-bound ref messages stamp the owning `viewId`; ref bridges keyed by `(viewId, channelId)`.
- `packages/pulse/js/src/messages.ts` and exported client type docs — wire type mirror of the Python changes, including the temporary `mountId`/`viewId` dual-field transition.

### Codegen / templates
- `packages/pulse/python/src/pulse/codegen/templates/layout.py` and any other codegen that emits `PulseView` JSX or wires the prerender payload — verify the path passed to `PulseView path={...}` is still the route pattern (`route_path`) and the prerender response is keyed accordingly. No semantic change; checked for safety.

### Tests
- `packages/pulse/python/tests/test_render_session.py` — most assertions on today's `route_mounts[path]` / `route_slots[path]` rewrite to `views[view_id]` / `active_by_path` / `pending_by_path`. Concurrent-pending scenarios become asserttable rather than impossible.
- `packages/pulse/python/tests/test_channels.py` — adopt internal-key resolution; assert `viewId` in route-bound wire messages.
- `packages/pulse/python/tests/test_refs.py` / `test_renderer.py` — concurrent same-route pending refs use separate view-scoped channels; stale ref events from disposed views drop.
- `packages/pulse/python/tests/test_forms.py` or `test_render_session.py` — pending view form submit promotes before handler execution; stale view form submit returns 410.
- `packages/pulse/python/tests/test_query_param.py` — `navigate_to` wire shape: `sourceViewId` only.
- `packages/pulse/python/tests/test_render_session.py` — API/JS pending futures unblock stale async callbacks; stale navigation from a closed source view drops/logs; unknown scoped messages do not call middleware.
- `packages/pulse/python/tests/test_render_session.py` — queued pending `navigate_to` drops on callback promotion; disconnect active→pending cancels/reschedules timeouts; reconnect replay uses fresh routeInfo; StrictMode timeout expiry disposes; prerender redirect disposes whole batch.
- `packages/pulse/js/src/client.test.ts` — `#views` keyed by viewId; attach-evicts behavior; channel viewId stamping.
- `packages/pulse/js/src/ref.test.ts` / `renderer.test.tsx` — ref mounted/unmounted/request messages include `viewId`.
- `packages/pulse/js/src/pulse-view.test.tsx` — wire assertions adjust.
- `packages/pulse/js/src/renderer.test.tsx` — callback invocation signature.

#### Prototype-discovered regression scenarios

These came from the first partial `mountId` prototype and should be preserved as named tests even if that prototype code is discarded:

- **Same-pattern prerender reset + delayed websocket diff.** Reproduce a route like `/sise/:quarryCode`: render QMOS from HTTP prerender, replace it with QCTV from a later same-pattern prerender, then deliver a delayed `vdom_update` for the QMOS `viewId`. The client must not throw, must not mutate the QCTV tree, and must leave the current view intact.
- **Renderer callback identity capture.** A button rendered under view A keeps a callback closure after the renderer is reinitialized for view B. Invoking the old closure must send A's `viewId`, not B's. Cover immediate callbacks, debounced callbacks, moved nodes, and callbacks whose eval prop is later removed.
- **PulseView mount/view-id swap behavior.** When prerender data changes for the same `route_path`, `PulseView` attaches the new `viewId`, resets the tree from the new HTTP baseline before stale content can paint, and later cleanup detaches only the view captured by that lifecycle. Route-info-only changes still send `update` for the same view.
- **Client stale server messages.** `vdom_update`, view-bound `server_error`, `js_exec`, `api_call`, and route-bound `channel_message` carrying an old `viewId` are dropped or answered with a stale/error result as appropriate. API/channel request stale errors must unblock server futures; they must not hang waiting for a response that will never arrive.
- **Pending view queues.** While a second same-pattern view is pending, VDOM diffs, render errors, and route-bound navigations for that pending view queue under its `viewId`. Attaching that view flushes its queue in order; stale messages for the previous active view do not flush into the new view.
- **Stale callback/detach isolation.** After pending view B promotes and disposes active view A, callbacks and detach messages for A are no-ops. They must not execute B's callback keys, mutate shared state through B, or dispose B.
- **Unscoped versus scoped path messages during migration.** During the dual-wire window, unscoped path messages target only the active view even if a pending sibling exists. Scoped messages with an unknown or stale `viewId` are dropped/logged. `vdom_update` without `viewId` is rejected once the wire requires view scope.
- **Form owner identity.** Manual and automatic form registrations store owner `viewId`; submit revalidates after body parsing. A stale form returns 410, a pending attached form promotes before handler execution, and disposal unregisters every form owned by the view.
- **Route-bound channel owner identity.** Route-bound channel messages carry `viewId`, cleanup removes only channels owned by that view, and a stale view's channel removal cannot close the current view's channel with the same raw channel id.
- **StrictMode replay identity.** Development `attach -> detach -> attach` reuses the same `viewId`, survives the short pending timeout, does not reload, and does not renew identity during the synthetic bounce.

### Docs / skills
- `skills/pulse/references/middleware.md` — document context dataclass middleware signatures and `route_path`/`view_id` fields.
- Middleware guide/tutorials, channel docs, client type docs, and `docs/content/docs/reference/pulse-client/components.mdx`, `hooks.mdx`, `types.mdx` — wire shape references and view terminology.

---

## Landing order

The migration is large enough that landing it as one PR would freeze the codebase. Sequence below keeps the test suite green at each step by being *additive* until the cutover (step 6), at which point the old fields drop in a single coherent change.

1. **Wire types: additive.** Add `viewId` to every wire message that needs it (`ClientUpdateMessage`, `ClientDetachMessage`, `ClientCallbackMessage`, route-bound `ClientChannelMessage`, etc.) without removing `path`, current `mountId`, or `sourceRoutePath`/`sourcePath`. During the rename transition, emit both `mountId` and `viewId`; server treats `viewId` as canonical and `mountId` as a temporary alias/fallback. Client stamps both. No behavior change.

2. **Server data model: dual-write.** Introduce `views` / `active_by_path` / `pending_by_path` alongside the existing `route_slots` / `route_mounts`. Rename `RenderSession.routes` to `route_tree`. Introduce `_dispose_view(reason)` and route all current disposal call sites through it. Views are written to both old and new structures; reads still go through the old structures. Retain old `idle` behavior during steps 2-8 unless pause/resume lands earlier.

3. **Forms migrate to `views.get(view_id)`.** Form-disposal hook added to `_dispose_view`. Pending form submit promotes before execution. Form tests updated.

4. **Channels and refs migrate to `(view_id, channel_id)` internal keys.** Server: `_channels_by_view` added, `_channels_by_route` removed, `PendingRequest.channel_internal_key` renamed. Route-bound ref channels join the same namespace. Missing `viewId` is tolerated only before concurrent pending route-bound channels are enabled; after that, missing `viewId` for a route-bound channel rejects/logs rather than falling back ambiguously. JS client: introduce `PulseViewContext`, update `usePulseChannel` / `acquireChannel` / ref registry signatures to accept `viewId`. Outbound channel and ref messages stamp `viewId`.

5. **App dispatch + middleware contexts.** Replace `middleware.message` / `middleware.channel` signatures with context dataclasses. Dispatcher normalizes `viewId → view → route_path/route_info` once per message. Unknown scoped views are handled before user middleware. User-facing middleware doc updated. Reads now flow through the new structures via the context.

6. **Client view map cutover, still dual-wire.** JS client switches `#views` to view-id keys with the attach-evicts rule, detach write guard, and routeInfo freshness. It still sends old path fields alongside `viewId`.

7. **Server view map cutover, still dual-wire.** Server reads through `views` / `active_by_path` / `pending_by_path`; delete `RouteSlot` / `route_slots` / old `route_mounts` once tests pass.

8. **Drop old wire fields.** Remove `sourceRoutePath`/`sourcePath` from `navigate_to`, remove path from view-scoped messages, and remove temporary `mountId` aliases. Change `ClientUpdateMessage`/`ClientDetachMessage`/etc. to view-only shape.

9. **Pending pause/resume + StrictMode cleanup.** Land `effect.pause()`/`resume()` on `active↔pending`. Drop the StrictMode server special case in favor of the standard pending-with-timeout, plus matching client-side delayed close/reacquire tolerance for route-bound channels and refs. Add server-side tombstones. Update docs (`skills/pulse/references/middleware.md`, the docs site reference pages).

After each step, `make all` should pass. Steps 1–7 keep the old wire behavior working through dual fields; step 8 is the wire-shape removal; step 9 is lifecycle/observability polish.

---

## Resolved open questions

1. **Promotion atomicity.** Synchronous, no `await`, indexes removed first. Runs outside reactive batches.
2. **Reconnect with pre-existing pendings.** All pendings get `max(remaining, disconnect_queue_timeout)` on disconnect via cancel-then-reschedule; their effects pause.
3. **Idle view eviction.** The `idle` state is dropped. Pendings dispose on timeout.
4. **Cross-pattern path collisions.** `active_by_path` keyed by `route_path` (pattern), not `pathname`. `#pathToViewId` mirror.
5. **Dev StrictMode replay.** Treated as a normal `_dispose_view` with a short delay; the view sits in `pending_by_path` during the window and the replayed `attach` promotes it. No invariant exceptions.
6. **Cross-render-session message arrival.** Drop silently for vdom_update/server_error/js_exec/api_call; reply `reload` for `attach`. Tombstone logged in dev.
7. **State/index ownership.** `_set_state` is the only state/index mutator; lifecycle methods never edit indexes directly.
8. **Non-websocket view-bound surfaces.** Forms, refs, and route-bound API/JS futures all carry or store owner view identity. Forms/refs use stale drop semantics; API/JS futures unblock callbacks even when the source view has closed.
9. **Async callbacks after view close.** Async callbacks continue after their source view closes. State writes and non-navigation side effects proceed; route-bound navigation from the stale source is dropped/logged.
10. **Late attach after timeout.** Full page reload is the intended v1 behavior.
11. **Terminology.** The protocol and design use `view_id` / `viewId`; old implementation names are migrated or treated as compatibility scaffolding during landing.
