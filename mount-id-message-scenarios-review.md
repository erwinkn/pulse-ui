# Adversarial Review — View ID Routing Design (v4)

Findings consolidated from four review angles: **concurrency**, **wire protocol**, **state machine**, **migration/DX**. Sorted by severity. Each entry: **Context + Problem + Proposed Solution**.

---

## CRITICAL

### C1. `_promote` is sync, but its callers await — two attaches can race

**Context.** Doc claims promotion is atomic. True *inside* `_promote`. But the path from message to `_promote` goes through async middleware: `await _handle_pulse_message → await middleware.message → _next → _promote`. python-socketio dispatches each event as its own asyncio task with no per-session serialization.

**Problem.** `attach(A)` and `attach(B)` for the same `route_path` arrive in quick succession. Both tasks await middleware. Task A wakes first, calls `_promote(A)` which disposes B as a sibling. Task B wakes, calls `_promote(B)` — but `views[B]` is gone. Per the pseudocode (`view = views[view_id]`), this is a `KeyError`. Even if `_next` revalidates and drops B silently, the client has already committed to B in `#views` and the server stays on A — silent divergence. The wire contract assumes attaches that arrive later supersede earlier ones; the implementation, under load, picks whichever lock-free task wins the await race.

**Proposed Solution.** Per-render-session async lock (`render._dispatch_lock`) held across the entire `_next` body for view-mutating messages (attach/detach/callback/update/channel). Middleware runs *outside* the lock. `_promote` early-returns if `view.state == "active"` (idempotent) and never `KeyError`s on missing view. Document explicitly that "promotion atomicity" relies on this lock, not just `_promote`'s no-await body.

---

### C2. `flush_queue(send_message)` inside `_promote` — `sio.emit` is async, breaking the "no await" claim

**Context.** Step 4 of `_promote`: `view.flush_queue(send_message)`. `send_message` ultimately wraps `sio.emit` which is async. Today's `RouteInstance.activate` papers over this with fire-and-forget `create_task`.

**Problem.** If the implementer writes `await send_message(msg)` (the correct ordering choice), promotion ceases to be synchronous and every concurrency invariant collapses. If `send_message` stays fire-and-forget, ordering between queued ops and inline subsequent emits is undefined — small inline emits can leapfrog large queued batches.

**Proposed Solution.** Make the contract explicit: `flush_queue` is sync and `send_message` is a fire-and-forget enqueue onto a **per-render-session ordered outbound queue** drained by a single writer task that awaits `sio.emit`. Document this queue — it's currently a load-bearing assumption stated nowhere.

---

### C3. Disconnect race: `_promote` runs after `_send_message=None`, silently drops queued ops

**Context.** Disconnect handler runs as its own asyncio task. A message-handler task may be inside middleware (mid-await) when disconnect fires.

**Problem.** Timeline: (1) `attach(B)` task awaits middleware. (2) Socket drops; disconnect handler runs, transitions A to pending, pauses A's effect, sets `render._send_message = None`. (3) `_promote(B)` resumes, calls `flush_queue(send_message)` where `send_message` is now `None`. Queued vdom_updates are silently dropped. View B is marked active with no client connection. On reconnect, the server thinks B is fine; the client has B in `#views` but never received the initial diff. The view is permanently broken until next nav.

**Proposed Solution.** `_promote` must check `if render._send_message is None: refuse to promote; keep view pending; defer until reconnect`. Pair with C1's lock so disconnect either waits for in-flight promotions or invalidates them cleanly.

---

### C4. `_dispose_view` idempotency contradicts tombstone semantics

**Context.** `_dispose_view` is documented as idempotent ("returns if view_id not in views or state == closed") and also "records the tombstone, cancels the timeout, calls `_set_state(view, "closed")`".

**Problem.** If anything between "record tombstone" and `_set_state("closed")` raises, the tombstone is recorded but the view stays in `views`. A second `_dispose_view` call then doesn't early-return (view still in `views`, not yet closed) and records a *duplicate* tombstone, overwriting the original `reason`/`disposed_at`. Debugging produces wrong attribution ("session_close" overwrites "timeout").

**Proposed Solution.** Set `state = "closed"` **first**, before any cleanup that can raise. Then record tombstone. Then run cleanup. Order: state mutation → tombstone → cleanup. Idempotency on `state == "closed"` then actually works. Also guard tombstone insert with `if view_id in tombstones: bump timestamp; keep original reason`.

---

### C5. "Index-first disposal" contradicts "`_set_state` is the only mutator"

**Context.** Invariant table says disposal is "index-first": indexes removed *before* state change. Separately: `_set_state` is the sole mutator of state + indexes. Body of `_dispose_view` calls `_set_state(view, "closed")` which atomically removes from indexes *and* sets state.

**Problem.** Three rules form an internal contradiction. There is no "index-first" anywhere in the implementation the doc describes — index removal happens *as part of* the state mutation. Two implementers reading this will produce different sequences; tests written against either pass the other's bug.

**Proposed Solution.** Pick one model and rename the invariant. Recommended: "Cleanup-last disposal — state and indexes mutate atomically via `_set_state`, *then* cleanup runs." Or, if "index-first" is genuinely required (to prevent cleanup observing an active-looking view), split `_set_state(view, "closed")` into `_unindex(view)` followed by `view.state = "closed"` and document the two-step.

---

### C6. View creation has no atomic spec — "exactly one index" window violation

**Context.** Invariant: a view in `views` is in exactly one of `active_by_path` or `pending_by_path`. State machine starts at `pending → active → closed` with no described precursor.

**Problem.** If view creation is `views[id] = view; pending_by_path[rp].add(id); view.state = "pending"` as three statements with any `await` between (prerender middleware, async route context construction), another coroutine can observe a view in `views` that isn't in any index. Invariant silently violated under concurrency. Tests don't catch it because they sample post-creation.

**Proposed Solution.** Add `_create_view(route_path, ...)` as the sole creation mutator: inserts into `views`, adds to `pending_by_path[rp]`, sets `state="pending"` — synchronously, no `await`. All async setup (running middleware, building context) happens *before* the view is inserted. Add an assertion: `views.get(view_id) is not None ⇒ view in exactly one index`.

---

### C7. viewId generation method is unspecified — security claim is unenforced

**Context.** Doc states viewIds are "server-minted, unguessable, scoped to one RenderSession." Codebase currently uses `uuid.uuid4().hex` for `mount_id`. Doc never says what `view_id` generation uses.

**Problem.** "Unguessable" is asserted as a security property but never specified. If someone optimizes to a counter, the property silently degrades. There's no specification of the wire alphabet/length, so clients can't validate shape defensively.

**Proposed Solution.** Specify: "viewIds are generated via `secrets.token_urlsafe(16)` (≥128 bits of cryptographic entropy). Server MUST reject any viewId from the wire that fails a syntactic shape check before any map lookup, to prevent map-pollution DoS via attacker strings." Add a unit test that the generator is cryptographic.

---

### C8. Socket↔render-session binding is unauthenticated for cross-tab scenarios

**Context.** "The dispatcher must reject any `viewId` not present in `render.views` for that render session; a syntactically valid ID from another session is stale."

**Problem.** This is correct *if* the socket→render binding is itself authenticated. If two tabs share a session cookie/sid (common — same browser, same login) and share a `RenderSession`, tab A can send `attach(viewId_from_tab_B)` and the server will find it and promote/dispose B's view. That's same-session cross-tab DoS, not "stale."

**Proposed Solution.** Add a "Session binding and tab isolation" section. Specify either (a) each socket connection gets its own `RenderSession` — make this explicit — or (b) if sessions can be multi-socket, every `views[viewId]` records the originating socket id and the dispatcher checks `view.socket_id == incoming.socket_id` before mutation.

---

## HIGH

### H9. Reactive batch flush + `_promote` reachability

**Context.** Invariant: "`_promote` runs outside the reactive batch." Mechanism: "invoked only from message handlers and timer callbacks." Doc says `_promote` and `_dispose_view` "assert they are not running inside reactive batch flush."

**Problem.** "Inside a batch" and "inside `flush_effects()` iteration" are different states; conflating them produces wrong asserts. Many message handlers today wrap callback execution in `with batch():` — a naive `assert not in_batch` fires on correct usage. The *actual* hazard is mid-iteration: disposing a sibling effect while another effect is iterating.

**Proposed Solution.** Add a thread-local `IS_FLUSHING: bool` in the reactive runtime. Set true at top of `flush_effects()`, false at bottom. `_promote`, `_dispose_view`, and `effect.dispose()` assert `not IS_FLUSHING`. Stop checking "inside a batch" — irrelevant. State this in the doc and audit every emit/dispatch path that could call `_promote`/`_dispose_view`.

---

### H10. Pause/resume not balanced across bounce; `resume()` schedules a run

**Context.** Doc: "Effect resumes on `_promote`. Safe no-op if already running." Disconnect: pause. Promote: resume.

**Problem.** `effect.pause()` and `effect.resume()` are idempotent setters of a `paused` flag, not balanced counters. `resume()` on a paused effect schedules a fresh run (per `reactive.py:498-501`); on an already-running effect, it's a no-op. The doc's "safe no-op if already running" is misleading — it's only no-op when not paused. Repeated disconnect/reconnect bounces produce extra effect runs or, worse, drop pending intervals if `pause()` cancels them (`reactive.py:492-501`).

**Proposed Solution.** Pin down exact semantics: "Each `_promote` calls `resume()` once; each `active→pending` calls `pause()` once; both idempotent." Audit `reactive.py:492-501` and either harden `pause()` to early-return when already paused or document the cancel-on-pause side effect. Add a bounce regression test: disconnect↔reconnect 5x, assert effect runs exactly the expected count.

---

### H11. Pending timeout generation check needs an explicit counter

**Context.** "Pending timeout callbacks are generation-checked: the callback only disposes when `view.state == "pending"` AND the firing timer handle/generation is still the view's current `queue_timeout`."

**Problem.** Ambiguous between "handle identity comparison" and "explicit generation counter." Handle-identity works *only* because `_promote` is truly synchronous (no yield between cancel-and-reschedule and any timer callback). If `_promote` or `_dispose_view` ever introduces an await — e.g. C2 implementation lapses — the handle-identity check stops being sufficient. Also brittle to future refactors (timer pooling, mock clocks).

**Proposed Solution.** Mandate `view._timeout_gen: int` incremented on every cancel/reschedule. Callback closures capture `gen` at schedule time and compare `gen == view._timeout_gen` on fire. Spell this out in the doc rather than hand-waving "generation-checked."

---

### H12. `queue_timeout` lifecycle isn't spec'd across state transitions

**Context.** Multiple transitions reference timer cancellation/scheduling but no single contract.

**Problem.** Unspecified: does `_set_state(view, "active")` clear `queue_timeout`? Does `active→pending` on disconnect cancel anything (previously active so should be `None`, but unstated)? Does idempotent re-disposal cancel `None` or a stale handle?

**Proposed Solution.** Add `queue_timeout` to the `_set_state` contract:
- `_set_state(view, "active")`: assert `queue_timeout is None`; otherwise cancel and clear.
- `_set_state(view, "pending")`: caller responsible for scheduling; assert previous is cleared.
- `_set_state(view, "closed")`: cancel and clear `queue_timeout` before index/state mutation.

Single home for the generation-check rule: timer callback checks `view._timeout_gen == captured_gen`.

---

### H13. Same-pattern nav during disconnect causes unintended hard reload

**Context.** Disconnect handler converts active → pending with 300s timeout (designed to survive flaky network). Client "attach-evicts" rule: a new attach for the same routePath deletes the old viewId from `#views`. Reconnect replay iterates `#views`.

**Problem.** Timeline: (1) Socket disconnects; A is pending server-side. (2) Client navigates same-pattern; React mounts new `PulseView` with new viewId B. Client eviction removes A from `#views`. attach(B) and detach(A) queued for later send. (3) Reconnect replay sends only attach(B). Server has no record of B (created client-side during disconnect). Result: server replies `reload`. The 300s disconnect-timeout was designed to prevent exactly this case.

**Proposed Solution.** Pick one path:
- (a) Don't evict A from `#views` until server ack'd attach(B). On reconnect with both present, replay attach(A) (still pending server-side, promotes); B (unknown) reloads → at worst the user-pre-disconnect view restores. Make A "win" during transient disconnects.
- (b) Document explicitly: same-pattern nav during disconnect always reloads. Accept the limitation.

Currently the doc states three invariants ("same-pattern never sends detach", "reconnect replay by viewId", "unknown attach → reload") that combine into the worst outcome.

---

### H14. Reconnect replay drops queued route-bound `navigate_to` silently

**Context.** Promotion drops queued route-bound `navigate_to` messages with a dev warning ("user action wins over stale pending nav"). Reconnect goes through promotion.

**Problem.** While disconnected, server code on view X queues `ps.redirect("/settings")` as a `navigate_to`. On reconnect, replay-attach promotes X and drops the nav. The user expected redirect-to-settings but stays where they were with no signal that a redirect was intended. The "user action wins over stale nav" rule was designed for callback-triggered promotion, not reconnect replay.

**Proposed Solution.** Distinguish promotion reasons. `_promote(view_id, reason)`: for `reason="callback_promoted"` and `"form_promoted"`, drop queued navs (user action wins). For `reason="reconnect_replay"`, flush queued navs — they represent intended state changes.

---

### H15. Form submit during disconnect returns 410, causing user-visible flakiness

**Context.** Form handler: if `view.state == "pending"` and `render._send_message is None`, return 409/410.

**Problem.** User submits form → handler resolves view A (active) → `await request.form()` → during await, WS blips for 200ms → handler revalidates, sees pending + no sender → 410. User sees form failure for a transient blip. They retry, double-submitting. This contradicts the design goal that disconnect-pending should survive flaky networks.

**Proposed Solution.** Form handler waits on `view._attached_event = asyncio.Event()` with a bounded timeout (e.g. 5s) for the view to reattach. If reattached within the window, promote and execute. Falls back to 410 only after sustained disconnect. Alternative: register a `view.on_promote` continuation. Either way, ride out short disconnects.

---

### H16. Async callback futures (api/js) can hang on view disposal

**Context.** `_dispose_view` does not cancel callback work. Pending future's `owner_view_id` is checked when result arrives. Doc says client *should* send stale-error result when view is gone, "so the server future does not hang."

**Problem.** Load-bearing requirement on client. If the client misses this path (bug, version skew, network drop *after* `js_exec` send but *before* the reply), the future hangs forever, holding references to the closed view and defeating cleanup. No timeout in the contract.

**Proposed Solution.** Mandate a default timeout on `PendingClientRequest` (e.g. 60s). On view disposal, track futures owned by view; shorten their remaining timeout to a small value (e.g. 5s) since the owning callback is on a faster-failure path. Reject (not cancel) on expiry with a typed `StaleViewError`.

---

### H17. Cleanup that emits messages or re-enters disposal is unspecified

**Context.** `_dispose_view` cleanup unmounts the tree and disposes the effect. Tree unmount triggers hook cleanups, which can emit `__close__` channel messages or write to signals.

**Problem.** Several failure modes: (a) Effect disposal during another effect's `flush_effects` iteration crashes (same hazard as `_promote` mid-batch). (b) A child hook cleanup writes a signal observed by another view's effect, triggering emissions that read stale `ctx`. (c) `_dispose_view` "contains no `await`" — strong claim; need to verify tree unmount, ref cleanup, channel close are all sync.

**Proposed Solution.** (a) Add `assert not IS_FLUSHING` to `effect.dispose()` (per H9). (b) Document the cleanup order — tombstone → cancel timer → unindex → state=closed → unmount → dispose effect — and that each step is exception-isolated. (c) Add a test that wraps `_dispose_view` in instrumentation that flags any `await`.

---

### H18. Async callbacks writing through stale `ctx` after view close

**Context.** Doc: "Async callbacks continue running after source view closes. State writes still happen. Navigation from a stale source is dropped/logged."

**Problem.** A 10s async callback completes after `_dispose_view(A)`. It writes a signal. That signal's subscribers include effects on *other* live views. Those effects use `ctx` — but which `ctx`? If reading `ctx.source_view` referring to A, A is closed; if the wire-emit path stamps A's view_id, messages drop. Writes also affect view-local signals which may now be orphaned. Behavior is unspecified.

**Proposed Solution.** Specify: (a) Effects run under the `ctx` of their **owning view**, never the writer's `ctx`. (b) When `_dispose_view(A)` runs, mark all in-flight async callbacks owned by A with a `view_closed` flag readable by user code (`ctx.view.state == "closed"` post-await check). (c) Document the canonical async callback pattern with the post-await staleness check.

---

### H19. Dual-write window (steps 2-7) has no equivalence assertion

**Context.** Steps 2-7 maintain two parallel state representations (`route_slots`/`route_mounts` and `views`/`active_by_path`/`pending_by_path`). Writes go to both; reads start old, end new at step 7.

**Problem.** A state transition that updates `route_mounts` but skips `active_by_path` (or vice versa) silently corrupts the new structure while old tests keep passing. By step 7 the new structure ships bugs that only manifest under concurrent-pending workloads.

**Proposed Solution.** Debug-mode assertion `_assert_dual_write_coherent(render)` called at end of every state-mutating method during steps 2-7. Walks both structures, asserts they describe the same `(view_id, route_path, state)` tuples. Wired into the test fixture. Removed at step 7.

---

### H20. Step 4 (channels) lands before step 5 (middleware contexts) — broken intermediate

**Context.** Step 4 keys channels by `(view_id, channel_id)` and stamps `viewId` outbound. Step 5 adds `ChannelMiddlewareContext` with `view_id`. Between steps, channel middleware uses old `channel(channel_id, event, payload, request_id, session, next)` signature.

**Problem.** Post-step-4, channels are internally view-keyed but user middleware sees only `channel_id`. Any view-aware authorization can't be written. Worse, user middleware that re-resolves the channel by raw id collides across concurrent pendings — the exact bug step 4 fixes.

**Proposed Solution.** Either (a) merge steps 4 and 5 into one PR, or (b) in step 4, add `view_id` as an additional kwarg on the old middleware signature as a transitional shim, removed cleanly in step 5. Document signature-in-effect at each step boundary.

---

### H21. mountId/viewId dual-emission has no drift detection

**Context.** Step 1: emit both `mountId` and `viewId`. Server prefers `viewId`, falls back to `mountId`. Step 8 removes `mountId`.

**Problem.** Between steps 1 and 8, code emitting only `mountId` (legacy missed call site) or only `viewId` (new path) works due to fallback. At step 8, the missed call site silently breaks. No mechanism surfaces drift during the window.

**Proposed Solution.** During steps 1-7, server asserts `mountId == viewId` on every incoming message in dev mode, logs structured warning otherwise. Add a CI grep: "no message constructor emits one without the other." Optionally a precedence table in the doc for which wins when (the doc currently just says "canonical").

---

### H22. Middleware migration is more than a one-line signature change

**Context.** Doc: "Migrating user-written middleware is a one-line signature change."

**Problem.** Old `message(data, session, next)` exposed `data` as a raw dict. New `MessageMiddlewareContext` puts the message at `ctx.msg`, view fields on `ctx`. Any middleware introspecting `data["type"]`, `data["mountId"]`, etc. needs structural rewrite. Third-party middleware fails at import (TypeError) or first message (AttributeError). No migration guide.

**Proposed Solution.** Ship a MIGRATION.md with a before/after mapping table. Optionally add a `__init_subclass__` hook on `PulseMiddleware` that detects old positional signatures and raises with a pointed migration message. Stop calling it a one-line change.

---

### H23. Production observability is absent — only dev-mode tombstones

**Context.** Tombstones compile to no-op in production. Doc declines client tombstones entirely.

**Problem.** Production bug: "callbacks sometimes don't fire after navigation." Was it stale-view drop (intended), lookup bug, or wire corruption? No counter, no metric, no log. The class of bug view-id refactoring eliminates can't be confirmed without metrics.

**Proposed Solution.** Production-safe drop counter per session: `render.metrics.stale_drops_by_reason: dict[str, int]`. Or a structured log at INFO/WARN level for every stale drop with `{view_id, msg_type, reason, session_id}`. Tombstones can remain dev-only; *counts* and *reasons* must work in production.

---

### H24. Forced vs route-bound `navigate_to` distinguished by field absence

**Context.** Route-bound `navigate_to` carries `sourceViewId`; forced/global omits it. Client distinguishes by presence.

**Problem.** A server-side bug that forgets `sourceViewId` silently downgrades route-bound nav to forced (bypassing stale-source drop). Reverse: a future feature that wants "navigated by X but force-apply" is inexpressible.

**Proposed Solution.** Add explicit `scope: "view" | "forced"` to `navigate_to`. Route-bound requires `scope: "view"` AND `sourceViewId: string`. Forced requires `scope: "forced"`. Both fields validated; missing/inconsistent → log + drop. Same explicit-scope rule for `server_error`.

---

### H25. `update` route-pattern validation is hand-waved

**Context.** Invariant: "Mutates view's RouteContext only after validating incoming RouteInfo still matches the view's route_path pattern and derived path params/catchall."

**Problem.** "Match" is undefined. Does `/items/42` match `/items/:id`? Yes. Does `/items/42/edit` match `/items/:id` (for a layout view)? Maybe. Does the server re-run `matchRoutes` or regex the pattern? What about query/hash-only changes? Two implementers will diverge.

**Proposed Solution.** Specify: "An `update` is accepted if `RouteTree.match(pathname).route_path == view.route_path` for leaf views, OR `view.route_path` is a prefix segment of the matched chain for layout views. Query/hash differences always accepted. On mismatch, emit `server_error` (not silent drop) so the client can recover." Also: silent drops on `update` cause server/client URL divergence — surface them.

---

### H26. Prerender chain vs React tree divergence is unhandled

**Context.** "Every PulseView in the rendered tree gets its own viewId from the HTTP prerender. The prerender request must include the full chain of route patterns the React tree will render."

**Problem.** Three divergence modes: (a) Client React Router computes a different match than server `RouteTree` (route ordering, splat semantics, trailing slash). (b) Client middleware/loader updates URL between request and render (auth redirect). (c) Server route tree changed (hot reload in dev). Client renders for a chain the server didn't prerender → views with no server backing.

**Proposed Solution.** "Prerender chain reconciliation" section. Client verifies after first render that `matchRoutes(actualUrl)` matches the requested chain. On mismatch: send fresh prerender for corrected chain (over WS, even if step 9 not landed — correctness need). Prerender response includes the chain it produced; client compares vs requested.

---

### H27. StrictMode viewId persistence mechanism is unexplained

**Context.** "The replayed `attach` reuses the same `viewId`."

**Problem.** When React unmounts and remounts a `PulseView`, the new mount is a fresh component with no preserved local state. Where does the second `attach` get the *same* viewId from? Not explained.

**Proposed Solution.** Document the concrete mechanism. Most plausible: React Router caches `loaderData` (containing `viewId`) across the StrictMode bounce, so remount reads the same loader data. State this explicitly. Also: "if React Router invalidates the loader between the two mounts (e.g. revalidation triggered by a sibling), the second attach gets a different viewId and the server treats it as same-pattern nav, not StrictMode replay." Add a test that the contract holds.

---

### H28. Effects-pause invariant lands at step 9 but is listed from day one

**Context.** Migration step 9 lands `effect.pause()`/`resume()` and StrictMode cleanup last. "Retain old `idle` behavior during steps 2-8 unless pause/resume lands earlier."

**Problem.** The "Effects pause on active→pending" invariant is in the table from the start. During steps 2-8, disconnect leaves effects running on pending views (old `idle`). Concurrent pendings (step 2) without effect pause means N× queue growth per signal write. Tests that assert post-design semantics fail through steps 2-8.

**Proposed Solution.** Either land pause/resume in step 2 (it's small) so invariants hold throughout, or split the invariant table into "v1 (steps 2-8)" vs "v2 (step 9+)" columns. Currently the doc presents one table and a migration plan that doesn't satisfy it mid-flight.

---

## MEDIUM

### M29. `attach` with unknown viewId → `reload` is a DoS vector

**Context.** Unknown `viewId` on attach replies `reload`.

**Problem.** A misbehaving client (or attacker on an authenticated socket) spamming attaches with random viewIds forces `reload` storms. A buggy client `#views` desync triggering replay of historical viewIds produces the same effect.

**Proposed Solution.** (a) Server rate-limits `reload` emissions per session (e.g. max 1 per 5s; subsequent unknown attaches silently drop + dev-log). (b) Client deduplicates attach per viewId per connect cycle — never send `attach(X)` twice without a `detach(X)` between.

---

### M30. Channel `responseTo` mismatch can hang the future

**Context.** "`(viewId | None, channel, responseTo)` must match `PendingRequest.channel_internal_key`."

**Problem.** Doc says validate, but doesn't say what happens on mismatch. If the server-side future never resolves, the awaiting coroutine hangs. `api_result`/`js_result` solve this with "stale/error result unblocks the future"; channels should mirror.

**Proposed Solution.** Specify: "Channel response with mismatched key rejects the pending future with a `ChannelScopeMismatch` error and logs. Disconnect-time, pending channel futures owned by closed views reject; futures owned by still-active views await reconnect timeout."

---

### M31. Partial prerender chain failures: redirect/notFound precedence

**Context.** "If any path in the requested chain redirects or returns not-found, the whole prerender batch returns that redirect/not-found and disposes every view created by the batch."

**Problem.** Which redirect wins if two views in the chain both redirect to different paths? Order unspecified. Partial chain (parent OK, child not-found) handling unspecified.

**Proposed Solution.** Specify deterministic precedence: "Layouts execute top-down. First view returning redirect/not-found short-circuits the chain; subsequent views don't execute. Already-created views in the chain are disposed in reverse order with `reason='prerender_batch_failed'`." Add tests for `[layout-redirects, child-would-redirect]` → response is layout's redirect.

---

### M32. Prerender batch atomicity — already-created views observable mid-batch

**Context.** Batch creation is sequential; on failure, "disposes every view created by the batch."

**Problem.** Mid-batch, prior views are already in `views` and `pending_by_path` and observable by other code paths (a sibling tab's reconnect replay, a parallel HTTP request validating channel scope). The doc doesn't specify how the disposal list is tracked.

**Proposed Solution.** Wrap batch in try/except tracking `created_view_ids: list[str]` during construction. On failure or redirect/notFound, iterate in reverse and `_dispose_view(reason="prerender_batch_failed")`. Add a test where the page view raises mid-creation → layout view is disposed.

---

### M33. `vdom_update` ordering vs `attach` ack is unspecified

**Context.** Server queues vdom_updates for pending views; flushes on promotion.

**Problem.** Does the server send an explicit `attach_ack` or is the first `vdom_update` an implicit ack? If client adds viewId to `#views` *after* sending wire attach, vdom_update arriving immediately gets dropped as unknown.

**Proposed Solution.** Client adds viewId to `#views` **before** sending wire `attach`. Any inbound `vdom_update(X)` arriving right after attach finds X in `#views`. State this ordering explicitly in the attach-evicts invariant.

---

### M34. Stale error wire shape is not canonical

**Context.** "Stale/error result" appears in API/JS contexts; "ChannelScopeMismatch" suggested above.

**Problem.** Each error type has a different shape, making user-facing error handling brittle.

**Proposed Solution.** Canonical `StaleViewError` wire shape: `{ id, viewId, ok: false, error: { code: "stale_view", message, viewId } }`. Apply to `api_result`, `js_result`, channel `responseTo` errors. Server raises typed `StaleViewError` exception.

---

### M35. `ctx.source_view_id` contract contradicts public-vs-internal label

**Context.** "User-facing surfaces" lists `ctx.source_view_id` as "framework-internal identifier."

**Problem.** Either it's public (users will write code against it, can't change) or internal (shouldn't be on `ctx` at all). Doc design principle ("path is for humans, view_id internal") violated by exposure.

**Proposed Solution.** Pick: (a) rename `_source_view_id`, expose only `ctx.source_path` publicly; or (b) commit to it being public, remove "framework-internal" label. List explicitly which `ctx.source_*` fields are stable across versions.

---

### M36. `usePulseChannel` semantics silently change inside routes

**Context.** Hook now reads `PulseViewContext`. Inside a route → route-bound channel. Outside → session-bound.

**Problem.** Existing apps using `usePulseChannel` inside a route get session-bound semantics today. After refactor, they get route-bound. Same call site, different wire shape, different keying. Channels that previously persisted across same-pattern nav now get torn down on promotion. Breaking behavioral change advertised as additive.

**Proposed Solution.** Document the breaking change in the changelog. Provide opt-out: `usePulseChannel(channelId, { scope: "session" })` to preserve old behavior. Mention prominently in migration notes.

---

### M37. Channel scope ambiguity at registration is "prefer failing", not enforced

**Context.** "A raw channelId may not be registered as both session-bound and route-bound in one render session unless...". "Prefer failing on ambiguity."

**Problem.** "Prefer" is soft. If both registrations coexist, a client message with `channel: "chat"` and no viewId or scope falls through to session-bound — an adversarial route-bound client can omit viewId to address the session channel by accident or design.

**Proposed Solution.** Either (a) prohibit dual-registration entirely (fail closed), or (b) require `scope` to be explicit on every channel message; messages with neither viewId nor `scope: "session"` are malformed-rejected. Pick one.

---

### M38. Channel registration ambiguity from user POV is undocumented

**Context.** `ps.channel("chat")` in a route binds route-scope; same call in session-level binds session-scope.

**Problem.** Refactoring a chat feature from route to session (or vice versa) silently changes the channel key. Old subscribers stop receiving. No warning at refactor time.

**Proposed Solution.** Dev-mode warning when `ps.channel(id)` is called both session-scoped and route-scoped within one render session. Document the gotcha with before/after in the channels guide.

---

### M39. Middleware revalidation drops after side effects

**Context.** "`_next` revalidates the target view immediately before dispatching. If viewId no longer resolves, drops."

**Problem.** Middleware writes session state (audit log, rate counter) then calls `_next()`. Revalidation drops the message; side effects persist. Audit shows a callback that never executed; the middleware thought it authorized a real view.

**Proposed Solution.** (a) Document the contract: "middleware side effects must be idempotent or tolerant of post-`_next` view disposal." (b) `ctx.is_view_live()` as a cheap pre-mutation check. (c) Make `_next` return `Dropped(reason)` rather than silent swallow so middleware can roll back.

---

### M40. Two-guard staleness coverage is asserted but not enumerated

**Context.** "Stale dispatch detected via both `views.get(view_id) is None` AND `view.state == "closed"`."

**Problem.** Three reference-capture sources listed (effects, hook cleanups, async callbacks) but no normative table mapping every emit/dispatch path to which guards it uses. Channel outbound? API/JS pending resolve? Query param sync (uses guard 1, not 2 — race possible)? Form? Each needs classification.

**Proposed Solution.** Add a normative table:

| Emit/dispatch path | Guard 1 (views.get) | Guard 2 (state=="closed") | Notes |
|---|---|---|---|
| Callback dispatch | yes | yes (post-await) | … |
| Channel outbound | yes | yes | … |
| API/JS future resolve | n/a (owner_view_id) | n/a | future-side only |
| Form handle_submit | yes | yes (twice) | … |
| Query param sync nav | yes | needed (race) | … |

Catch "unclassified" paths during review.

---

### M41. Concurrent same-pattern nav triggers are unnamed

**Context.** Goal #3: "Support multiple concurrent pending views per path so racing prerenders and rapid same-pattern navigations never corrupt state."

**Problem.** "Racing prerenders" and "rapid nav" are vague. Without concrete triggers, neither author nor reviewer can verify coverage.

**Proposed Solution.** Enumerate triggers:
- Hover-prefetch + click
- Double-click on a Link
- Browser back/forward fast-press
- Suspense fallback re-mounting
- Server-driven `navigate_to` racing user-driven nav

Map each to a named test in the test checklist.

---

### M42. Test matrix for new concurrency invariants is generic

**Context.** "Concurrent-pending scenarios become assertable." Tests-section lists files, not test names.

**Problem.** "Promotion atomicity (synchronous)" is load-bearing but no specific test name. Same for "effects pause on active→pending and resume on promote", "disconnect-reconnect-disconnect pause/resume balance", "dual-write invariant holds."

**Proposed Solution.** Inline test checklist in the doc with named functions:
- `test_promote_disposes_siblings_synchronously_no_await` — instrumented `_dispose_view`, fail on any `await`.
- `test_effect_pause_resume_balanced_across_repeated_disconnects` — 5x bounce, count equal.
- `test_dual_write_invariant_holds_after_every_lifecycle_op` (steps 2-7 only).
- `test_middleware_revalidation_drops_when_view_disposed_during_await`.
- `test_concurrent_pending_channels_dont_collide_on_same_id`.

Each step's PR checks off relevant rows.

---

### M43. Tombstone LRU eviction is silent

**Context.** "Bounded LRU (last 100 entries per session)."

**Problem.** Stress test or long session with 250+ views evicts oldest tombstones first. Most interesting stale-message debug case (late message arriving 30 min post-disposal) has already lost its tombstone. Eviction itself is invisible.

**Proposed Solution.** (a) Cap by age (e.g. 5 min), not count — stale messages arrive within seconds, age-based avoids churn-eviction. (b) Or two-tier: unbounded count of `{view_id → (reason, disposed_at)}` for 60s, plus bounded LRU of full tombstones for 100. (c) Configurable limit. (d) Eviction counter exposed at `render.tombstone_stats`.

---

### M44. Pending prerender backlog has no overflow cap

**Context.** Prerender creates pending views with 60s timeout. User abandons before WS attach → pending sits 60s.

**Problem.** Adversarial or buggy client can DoS by repeatedly prerendering the same route — `pending_by_path[/foo]` grows unboundedly until 60s ticks.

**Proposed Solution.** Per-path soft cap (e.g. 10 pendings). Overflow disposes the oldest with `reason="pending_overflow"`. Combined with M29's reload rate-limit, bounds attacker amplification.

---

### M45. Compatibility aliases lifetime is unspecified

**Context.** "Rename `RouteInstance`/`RouteMount` aliases to `RouteView` where they are public, or keep compatibility aliases until cleanup." Similarly for `ctx.mount`.

**Problem.** "Until cleanup" is unbounded. The landing-order section doesn't name a step where aliases get removed. Permanent cruft contradicts `CLAUDE.md`'s "No backwards compatibility unless instructed."

**Proposed Solution.** Either (a) delete aliases in step 8, listed explicitly. Or (b) commit upfront to no aliases — Pulse has no external user base depending on `ctx.mount`; break it cleanly. Decide before step 2.

---

## LOW

### L46. No DevTools / inspection surface for new state

**Context.** New concurrent pendings, tombstones, dual-write window, internal-keyed channels — many invisible structures.

**Problem.** "Why is my channel not receiving — is the view pending or active?" requires `print` statements in framework code. Step 8 lands without anyone being able to interactively answer "what views exist right now for this session?"

**Proposed Solution.** Dev-mode endpoint `GET /_pulse/debug/session/{session_id}` returning view list (`{view_id, route_path, state, age_ms, channels}`) and tombstones. Client helper `window.__pulse__.snapshot()` for `#views`/`#pathToViewId`/`#channelsByView`. Land in step 9 alongside tombstones.

---

### L47. `detach` with unknown viewId behavior unspecified

**Context.** Scenarios matrix has "Delayed stale wire message" for vdom_update/server_error but not `detach`.

**Problem.** Client sends `detach(X)`; X is unknown (already disposed by sibling promote, or racing with StrictMode timeout). Server response unspecified.

**Proposed Solution.** Specify: "`detach` with unknown viewId is silently no-op (idempotent); tombstone-logged in dev." Also: `detach(viewId)` doesn't validate route_path on server (viewId is canonical).

---

### L48. `update` rejection has no client-visible feedback

**Context.** "Invalid updates drop/log."

**Problem.** Server drops `update` because RouteInfo doesn't match pattern. Client never finds out. PulseView's route-sync effect believes the server has new info; subsequent callbacks see stale state. Silent client-server URL divergence.

**Proposed Solution.** For `update` mismatch, emit `server_error` with `viewId` and code `update_rejected`, plus expected-vs-received hint. Or, for leaf-view-pattern mismatch, `reload` (heavier hammer, but pattern mismatch usually means the route tree shifted).

---

### L49. `RenderSession.routes` rename has no deprecation hint

**Context.** Step 2 renames `routes` to `route_tree`. "This is an intentional internal breaking change."

**Problem.** Any code reaching into `render.routes` produces `AttributeError` at runtime, not import. Conditional code paths may not surface until production.

**Proposed Solution.** During step 2 only, add `__getattr__` on `RenderSession` returning `self.route_tree` for `routes` and emitting `DeprecationWarning`. Remove shim in step 8 alongside other cleanup. 5 lines, surfaces breakage at first access.

---

### L50. Multi-transport reconnect (polling→websocket) can fire two attach waves

**Context.** "On `socket.on('connect')`, replay an `attach` for every entry in `#views`."

**Problem.** During socket.io transport upgrade (polling → websocket), the client may briefly see both transports active and fire `connect` twice. Two waves of attach replays; second wave hits already-active views. Doc's `_promote` doesn't have an explicit "already active" guard; `_set_state` asserts "no different active view" but doesn't say what happens on `active → active`.

**Proposed Solution.** `_promote` early-returns if `view.state == "active"` (idempotent). `_set_state` is a no-op when `view.state == new_state`. Spell out in doc.

---

## Structural recommendations

Three changes would resolve clusters of findings:

1. **Per-render-session async lock** wrapping `_next` body for view-mutating dispatches. Middleware runs *outside* the lock. Fixes C1, C3, H13 (partial), and many others.

2. **Explicit `view._timeout_gen: int` counter** for pending timeouts, captured by closures. Fixes H11, H12, related races.

3. **`_promote` guards: `_send_message is None` refuses; `state == "active"` early-returns idempotently.** Fixes C3, L50.

Plus:

4. **Explicit outbound message queue** (single writer task draining via `await sio.emit`). Makes "promotion is synchronous" survive the `sio.emit` async boundary. Fixes C2.

5. **Normative classification tables** (two-guard coverage M40, named tests M42, dual-wire precedence H21, channel scope H24) replace prose hand-waves.

6. **Production-safe drop counters** (H23, M43) separate from dev tombstones, so production debuggability survives.

7. **Pause/resume in step 2, not step 9** (H28) — small change, lets invariants hold throughout migration.

The destination design is internally coherent. The danger zones are (a) the async/await assumptions that promotion atomicity quietly depends on, (b) the migration window where invariants are partial, and (c) the dev-vs-prod observability split that hides production drops.
