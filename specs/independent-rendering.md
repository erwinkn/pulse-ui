# Independent rendering architecture (experimental)

## Status

Design draft. No public API or compatibility guarantee.

## Goal

Render an active branch and one or more candidate branches independently. A candidate may preserve active hook state, but cannot mutate or dispose the active branch before commit.

This is Pulse's equivalent of React's alternate tree: a second, unpublished tree plus transactional hook state and lifecycle work.

## Why this needs a new ownership model

Today, each `RouteMount` owns one mutable `RenderTree`. Reconciliation mutates it in place, transfers the same `HookContext` to matching components, and immediately unmounts replaced nodes. Hook render-end methods may also dispose effects. Queries share a session store, but constructing an observer immediately changes its lifecycle and may fetch.

Cloning only the VDOM is therefore insufficient. Independent rendering requires isolation across:

- rendered nodes and callbacks;
- hook state and reactive dependencies;
- effects, cleanup, setup, refs, and unmounts;
- query observers and fetch intent;
- route input read during render.

## What Solid does differently

Stable Solid 1.9 implements transitions in its reactive graph rather than through an alternate component or VDOM tree. Its components normally run once; fine-grained computations update DOM bindings directly.

During a transition, Solid gives reactive nodes parallel slots:

| Committed | Transition | Purpose |
| --- | --- | --- |
| `value` | `tValue` | Signal/memo value |
| `state` | `tState` | Computation dirty state |
| `owned` | `tOwned` | Child computation ownership |

A global transition record tracks touched sources, deferred effects, pending resource promises, scheduled computations, and deferred disposal. Transition reads prefer `tValue`; writes update it without replacing the committed `value`. Pure computations run against transition state, while effects that would mutate the DOM wait.

Suspense resources add their promises to the transition. When no promise or scheduled computation remains, Solid:

1. promotes `tValue` to `value`;
2. promotes transition computation/ownership state;
3. disposes superseded owners;
4. runs buffered effects;
5. resolves the transition promise.

The committed DOM therefore remains visible while the candidate reactive graph advances. Solid can also time-slice pure computations through its scheduler.

Urgent writes do not use React-style tree conflict detection. If an active write touches a source already used by a paused transition, Solid updates the committed value and transition slot, then schedules affected transition computations again. This is closer to rebasing one global reactive transaction than aborting an immutable render snapshot.

Important limits:

- Solid has one ambient transition, not independent arbitrary candidate trees;
- nested transitions join the current transition;
- its mechanism covers values, computations, ownership, effects, and Suspense-aware resources—not arbitrary external mutation;
- there is no general multi-candidate commit/abort API;
- transition-safe DOM behavior depends on DOM writes being reactive effects that can be buffered.
- Solid stores can mutate their raw backing object before commit even though tracked property reads retain committed values; raw/untracked reads are not isolated.

Solid briefly tried a literal forked reactive graph before the stable overlay design. That experiment cloned downstream observer nodes into an `original -> fork` map, rebuilt graph edges, then merged forks back into their originals. It was replaced almost immediately by the simpler `tValue`/`tState`/`tOwned` model. This strongly favors transaction slots over cloning the whole reactive graph.

Sources: [Solid transition slots and commit](https://github.com/solidjs/solid/blob/d2f81d546d5dff37aa25e4fa224e2192efec8c1a/packages/solid/src/reactive/signal.ts#L85-L127), [Solid read/write overlay](https://github.com/solidjs/solid/blob/d2f81d546d5dff37aa25e4fa224e2192efec8c1a/packages/solid/src/reactive/signal.ts#L1301-L1398), [Solid Suspense runtime](https://github.com/solidjs/solid/blob/d2f81d546d5dff37aa25e4fa224e2192efec8c1a/packages/solid/src/render/Suspense.ts#L123-L209), [historical forked graph](https://github.com/solidjs/solid/blob/3623573b0dc91fb3560cec791440cd09e12d502b/packages/solid/src/reactive/signal.ts#L1232-L1292), and [Solid transition documentation](https://docs.solidjs.com/reference/reactive-utilities/start-transition).

Solid 2 is exploring implicit, multiple, entangled transitions with pending owner children and effect queues. It is still beta, so it is useful research rather than a stable compatibility target. See the [Solid 2 async RFC](https://github.com/solidjs/solid/blob/v2.0.0-beta.0/documentation/solid-2.0/05-async-data.md#L86-L110).

### Lesson for Pulse

Pulse should combine two mechanisms:

1. A structural `RenderBranch` for mutable VDOM nodes, callbacks, and hook topology.
2. A Solid-style `ReactiveTransaction` plus candidate `OwnerRoot` for signals, computed caches, dependency edges, effects, and cleanup.

This avoids cloning entire `State` objects. Managed reactive state keeps logical identity while its values and graph metadata get branch-local slots. Explicit fork adapters remain necessary only for opaque hook values and external resources.

## Scope

The first target is server-side candidate rendering within one `RenderSession`, process, and event loop. Threads require locks around every shared cache/state boundary. Workers require an external transaction coordinator and shared versions; mount-local locking is insufficient.

In scope:

- preserved state across active and candidate branches;
- candidate commit, abort, cancellation, and retry;
- keyed queries using a shared read-through cache;
- exact-once effects and cleanup;
- conflict detection against active state and query changes.

Not initially in scope:

- merging concurrent writes;
- speculative user effects;
- preserving arbitrary mutable Python objects without an explicit fork contract;
- parallel commits to the same mount;
- protocol changes for incremental candidate updates.

## Terms

**Render branch**: one internally consistent rendered tree, callbacks, hook state, dependencies, and observer scope.

**Active branch**: the branch currently published to the client.

**Candidate branch**: unpublished work derived from an active branch or created from scratch.

**Branch base**: the active branch and versions from which a candidate was forked.

**Commit generation**: monotonic mount-local version used for publication conflicts. This is separate from the client-visible View Revision.

**Lifecycle journal**: deferred effect, observer, ref, and unmount work produced while rendering a candidate.

## Required invariants

1. Rendering or aborting a candidate cannot change active output, callbacks, hook values, subscriptions, effects, refs, or resources.
2. Candidate callbacks are unreachable until commit.
3. User effects, cleanup, and unmounts run only after a successful commit.
4. Abort releases candidate-only allocations without running active cleanup.
5. Commit publishes one coherent tree. A client never observes mixed active and candidate state.
6. A candidate never commits output based on an invalid state or query snapshot.
7. Cleanup and effects run at most once for each committed lifecycle transition.
8. Losing or cancelled candidates cannot cancel work owned by the active branch or another candidate.
9. Callback maps remain reachable for every retained client revision, independent of branch lifetime.

## Ownership model

```text
RenderSession
├── QueryCache                         shared, session lifetime
└── RouteMount
    ├── active: RenderBranch
    ├── candidates: {candidate_id: RenderBranch}
    ├── commit_generation
    └── commit_lock

RenderBranch
├── tree: RenderTree
├── callbacks
├── hook context fork
├── reactive transaction + owner root
├── reactive read set
├── QueryObserverScope
├── route snapshot
├── lifecycle journal
└── base: BranchBase | None
```

`RouteMount.state` remains the transport lifecycle (`pending`, `active`, `suspended`, `closed`). Branch lifecycle is separate:

```text
preparing -> ready -> committed
                  \-> aborted
```

Only the active branch owns live user effects, refs, and committed query observers. A candidate owns staged descriptions of those resources.

## Candidate lifecycle

### 1. Fork

Under the mount commit lock, capture:

- the active branch identity and commit generation;
- a stable route snapshot;
- fork roots for the render tree and component hook contexts;
- versions of inherited reactive cells as they are read;
- a fresh observer scope and lifecycle journal.

Forking must be cheap. Structural nodes and hook namespaces are shared until first candidate mutation. Candidate writes always allocate branch-local state.

### 2. Render

Render only into the candidate:

- reconciliation creates a candidate tree rather than mutating active nodes;
- replacements append active nodes to a retirement journal instead of unmounting them;
- hook render-start/end update candidate state only;
- effect creation and removal produce lifecycle intents;
- query reads use the shared cache but observer changes remain staged;
- callbacks are stored only on the candidate.

The result is a `PreparedRender` containing the tree, callbacks, VDOM output or operations, read set, and journal.

### 3. Validate

Reacquire the commit lock and validate:

- the same active branch is still installed;
- the mount commit generation equals the branch base;
- every inherited reactive cell read by the candidate has the same version;
- every query cache record read by the candidate has the same version;
- the route snapshot is still current.

The generation check is the safe initial policy. Per-cell validation allows a later implementation to avoid conflicts from unrelated state changes. A global reactive epoch alone is too coarse.

On conflict, abort and retry from the new active branch. Retries are bounded; exhaustion falls back to a normal render or reports a render conflict error.

### 4. Commit

Commit has one structural publication point:

1. Freeze the candidate.
2. Validate its branch base and read set.
3. Prepare observer/ref promotion without invoking user code.
4. Swap `mount.active` to the candidate.
5. Increment commit generation and View Revision; install its callback history and ref/channel routing.
6. Publish output.
7. Activate new query observers.
8. Dispose retired subtrees and removed non-subtree effects, then start/update new effects.
9. Release the old branch after its retained callback revisions no longer reference it.

Steps after the swap may invoke user code and therefore cannot be rolled back. Errors are reported as commit/effect/unmount errors; the new structural branch remains active. Cleanup continues best-effort so one failure does not leak the rest of the journal.

Ref routing must exist before transport send because the browser may emit a ref-mounted event immediately. User ref callbacks remain deferred until publication. Callback maps are copied into mount-level revision history before send; older retained revision maps outlive the old render branch.

Each lifecycle resource has exactly one journal owner. Retired subtree unmount is the sole disposer of hooks inside that subtree. The separate removed-effect journal contains only effects from retained nodes, preventing double cleanup. All old cleanup completes before any new user effect starts.

### 5. Abort

Abort:

- removes staged observers, fetch intents, refs, and callbacks;
- cancels only candidate-owned tasks or leases;
- disposes candidate-created internal allocations;
- drops the candidate tree and journal.

Abort does not dispose shared active state, invoke active effect cleanup, unmount active nodes, or change a View Revision.

## Transactional reconciliation

Replace destructive reconciliation with a work-in-progress renderer:

```python
prepared = active.prepare(next_element, branch_context)
mount.commit(prepared)  # or prepared.abort()
```

The renderer clones only the modified structural spine. Matching `PulseNode`s receive forked hook contexts. Unchanged immutable values may be shared. Mutable `Element`, `PulseNode`, callback maps, hook contexts, and normalized child/prop collections cannot be shared after either branch writes them.

`unmount_element()` becomes two operations:

- `retire(node)` during candidate render: record a possible removal;
- `unmount(node)` after commit: perform cleanup.

Nodes created only in a candidate are discarded on abort using candidate disposal, not committed unmount semantics.

## Transactional and forkable hook state

Managed reactive state uses `ReactiveTransaction`; it does not need to clone its owning `State` object. Hook contexts still fork their namespace and per-render bookkeeping so the active and candidate hook topology cannot interfere.

Generic `deepcopy` is not safe for opaque hook state. It may contain tasks, channels, database handles, closures, or effects. Such values need an explicit resource protocol:

```python
class ForkableResource:
    def fork(self, context: ForkContext) -> ForkableResource: ...
    def commit(self, context: CommitContext) -> None: ...
    def abort(self, context: AbortContext) -> None: ...
```

The concrete API may use adapters or journals, but every hook needs an explicit policy:

| Hook state | Candidate behavior | Commit | Abort |
| --- | --- | --- | --- |
| Reactive `State` | Share identity; use transaction slots | Promote slots | Drop slots |
| `stable` | Fork entries; update candidate targets only | Publish candidate entries | Drop entries |
| Inline effects | Record desired effect identities and functions | Diff against active, cleanup/start | Drop intents |
| `setup` / `init` | Reuse candidate-safe value; otherwise barrier | Publish staged metadata | Drop staged metadata |
| Query results | Fork observer bound to candidate state | Attach observer | Drop observer |
| Refs | Allocate staged handle/handler intent | Register/replace | Drop intent |
| Custom hook | Registered fork adapter required | Adapter-defined | Adapter-defined |

Unknown non-empty custom hook state fails candidate preparation early. Immutable custom state may declare itself shareable; other state requires an adapter. Silent sharing would violate isolation.

### Reactive state overlay

Preserving object identity and isolating writes are in tension. The preferred model keeps a logical state identity while routing property signal access through the current `RenderBranch`:

```text
logical State
└── field cell
    ├── active value/version
    └── candidate overlay value/base_version
```

Reads use the candidate overlay when present, otherwise the active value and version. First write creates an overlay entry. Commit promotes overlay values atomically; abort drops them.

Unlike Solid's single ambient `tValue`, Pulse must support multiple candidates. Transaction slots therefore live in a branch-local map keyed by logical reactive node, or on each node keyed by candidate ID. A shared unkeyed transition slot would let candidates overwrite each other.

Reactive containers need the same behavior. `ReactiveList`, `ReactiveDict`, `ReactiveSet`, and nested managed values mutate in place without assigning their State field. Their backing storage and structural signals must be branch-aware, or the value must clone/COW on its first nested write. Sharing a mutable container between branches is forbidden.

Promotion installs every changed cell and the new branch dependency set as one commit operation. It then notifies external observers while excluding the committing render effect, whose output already contains those values. Session-scoped observers in other mounts are scheduled normally. Process-global state is a candidate barrier in the first version because mount-local validation cannot serialize it.

This also supplies precise conflict detection. Each inherited read records `(cell, base_version)`. Computed values need branch-local caches because reading a computed mutates its cache and dependency set; validation ultimately uses its leaf signal versions.

Each candidate also owns an `OwnerRoot`. Computations and effects created while rendering attach there. Commit promotes its dependency/ownership graph and retires superseded owners; abort drops the root without touching active owners.

The first implementation invalidates a candidate when an active write changes its read set. A later Solid-style rebase can copy the urgent value into the transaction and rerun only affected candidate computations. Structural component rerenders still require branch reconciliation, so rebase is an optimization rather than the correctness foundation.

An eager clone may be used in the first prototype if it implements the same semantics. The public contract must not depend on eager copying.

### Purity boundary

Pulse cannot isolate arbitrary mutation such as `state._client.buffer.append(...)` or mutation of a value returned by `ps.setup()`. Candidate-safe code must obey one of these rules:

- mutate managed reactive fields only;
- use an immutable value;
- implement a fork adapter/resource protocol;
- mark the component or hook as a candidate barrier.

A barrier causes the candidate render to fall back to committed rendering for that transition. Development mode should identify the hook and component path.

`ps.setup()` may reuse an existing value when its key is unchanged. `ps.init()` storage also contains arbitrary Python objects, despite being represented as hook storage. Creating, re-keying, or mutating either kind of value cannot offer strict isolation unless the value is immutable, managed reactive state, or explicitly forkable. Otherwise both hooks are candidate barriers.

## Effects and cleanup

Candidate rendering uses a deferred-effect context. Creating an `Effect` produces a dormant descriptor; it does not subscribe, schedule, execute, or own cleanup.

Where possible, the descriptor is a computation under the candidate `OwnerRoot`, not a separate ad hoc journal entry. The lifecycle journal remains for non-reactive resources and structural retirement.

For each component, commit compares active and candidate effect identities:

- retained: update function/dependency intent without cleanup;
- removed: run active cleanup after publication;
- added: create and run after publication.

Abort drops descriptors. Effects never present in an active branch have no user cleanup to run.

Setup effects and state-owned effects follow the same rule. Candidate branch dependency capture is independent from the active render effect; promotion replaces the active dependency set atomically.

## Queries

Split shared data from branch ownership.

### Session `QueryCache`

One cache per `RenderSession`, keyed by normalized query key. A cache record owns:

- data, error, status, update time, and invalidation state;
- a monotonic cache version;
- shared request deduplication and request leases;
- cache lifetime metadata.

It does not own component callbacks, bound fetch functions, intervals, or branch observer identity.

### Branch `QueryObserver`

An observer owns:

- candidate-bound fetch function and callbacks;
- selected key and observer options;
- previous/placeholder/select view state;
- lifecycle: `prepared`, `committed`, or `disposed`.

A prepared observer may read cache data and records `(cache_key, cache_version)`. It does not affect active counts, GC, intervals, callbacks, invalidation, or fetching.

Query mutations are not reads. `invalidate`, `set_data`, `refetch`, enabled/key transitions, and infinite-page actions must produce commit intents or act as candidate barriers. They cannot mutate a shared cache record or start work during candidate render.

Initial fetch policy: record fetch intent and start it after commit. This gives strict isolation and simpler cancellation. Later, speculative fetch may be added if the cache owns the request and candidates hold leases. Completion may update the shared cache, but it cannot invoke prepared observer callbacks. Aborting one lease cannot cancel a request needed by an active observer or another candidate.

Unkeyed queries remain candidate-local or act as a candidate barrier in the first version. Sharing them requires separating their cache record from their observer, effectively giving them an internal key.

Cache updates during candidate rendering may rerender the active branch. They also invalidate candidates that read the old cache version.

## Route, session, refs, and external writes

Candidate rendering receives an immutable `RouteContext` snapshot. A route update during rendering invalidates the candidate.

Runtime APIs that mutate the session, navigate, send messages, execute JavaScript, register channels, or change forms are not ordinary hook state. During candidate render they must either:

- append a commit intent;
- operate on an explicitly candidate-owned resource; or
- fail as a candidate barrier.

Refs are staged because their current creation registers route channels and handlers. Candidate abort must never close or alter the active ref channel.

A candidate barrier fallback is serialized under the same commit lock. It advances commit generation and invalidates, cancels, or rebases sibling candidates before running the committed render. It is not a second uncoordinated publication path.

## Concurrency and reentrancy

- Candidate rendering may run concurrently; commit to one mount is serialized.
- Commit uses compare-and-swap semantics on active branch identity and generation.
- If two candidates share a base, at most one commits. The loser rebases or aborts.
- Detaching or closing a mount cancels all candidates before disposing the active branch.
- A state write or navigation triggered during post-commit effects schedules work from the newly active branch.
- Candidate cancellation is idempotent.

## Failure semantics

| Failure | Result |
| --- | --- |
| Render exception | Abort candidate; active branch unchanged |
| Redirect/not-found | Validate branch base under commit lock, then publish staged navigation; stale result aborts |
| Validation conflict | Abort and bounded retry |
| Candidate barrier | Fall back to non-speculative render |
| Commit preparation error | Abort; active branch unchanged |
| Effect/cleanup error after swap | Report; keep new branch; continue journal cleanup |
| Mount detach/close | Cancel candidates, then dispose active branch |

## Protocol impact

No protocol change is required for the first prototype. Candidates remain server-internal and publish through the existing init/update messages only after commit.

`viewId` continues to identify a mounted client view. `revision` continues to order client VDOM updates. Commit generation and reactive/cache versions remain server-internal.

If future navigation previews expose multiple server candidates to the browser, add an opaque candidate ID rather than overloading View ID.

## Implementation plan

### Phase 1: transactional renderer

- Introduce `RenderBranch`, `PreparedRender`, and lifecycle journal.
- Make reconciliation non-destructive.
- Defer unmounts and callback publication.
- Support stateless components and fresh candidates.

### Phase 2: forkable built-in hooks

- Add `ReactiveTransaction`, candidate `OwnerRoot`, and branch-aware reactive reads/writes.
- Implement branch-local containers, computed caches/dependencies, and `stable`.
- Add fork/commit/abort adapters for opaque hook resources.
- Reuse only candidate-safe init storage; barrier on arbitrary values.
- Add versioned read sets and mount commit lock.
- Treat setup resources, refs, and unknown custom hooks as barriers.

### Phase 3: deferred lifecycle

- Stage inline/state/setup effects and cleanup.
- Promote render dependencies atomically.
- Stage refs and other render-owned registrations.

### Phase 4: query split

- Separate `QueryCache` records from observers.
- Add prepared observer scopes and cache versions.
- Start fetch intents after commit.
- Port keyed and infinite queries; define unkeyed behavior.

### Phase 5: concurrent candidates

- Allow multiple candidates per mount.
- Add cancellation, bounded rebase/retry, diagnostics, and resource limits.
- Evaluate speculative cache-owned fetches.

Each phase ships behind an internal feature flag until its invariants pass stress tests.

## Test matrix

### Isolation

- candidate render exception leaves active tree, state, callbacks, and deps unchanged;
- abort runs no active cleanup or unmount;
- candidate callbacks cannot be invoked before commit;
- callback maps survive for retained client revisions after their branch retires;
- setup/init, ref, navigation, process-global state, and custom-hook barriers fail safely.

### Commit lifecycle

- state and callbacks publish atomically;
- nested list/dict/set mutation stays candidate-local;
- promotion notifies external observers without redundantly rerendering itself;
- retained effects do not restart;
- removed cleanup runs once after commit;
- added effects start once after commit;
- retired nodes unmount once;
- post-swap lifecycle failure does not restore the old tree.

### Conflicts

- active write to a read cell forces retry;
- Solid-style rebase reruns affected candidate computations when enabled;
- unrelated write may commit when precise validation is enabled;
- query cache and route changes invalidate stale candidates;
- two candidates from one base produce one winner;
- barrier fallback serializes publication and invalidates sibling candidates;
- retry exhaustion falls back deterministically.

### Queries

- active and candidate read one cache record through separate observers;
- prepared observer does not affect GC, interval, callback, or fetch state;
- abort cannot cancel an active fetch;
- commit attaches new observer before retiring old observer;
- dynamic key changes remain branch-local;
- query mutations stage or barrier without touching the shared cache;
- candidate callbacks never receive pre-commit completion.

### Mount lifecycle

- detach and session close cancel candidates safely;
- suspend/resume preserves only the active branch;
- StrictMode detach replay does not promote or leak candidates;
- render-loop accounting is branch-aware.

### Stress

- randomized render/write/abort/commit scheduling;
- cancellation at every candidate phase;
- journal operations remain idempotent under injected failures;
- no observer, task, timer, effect, ref, or hook-state leaks.

## Observability

Development diagnostics should include:

- candidate ID, mount path, base/current generation;
- render, validation, commit, abort, and retry timings;
- conflict source: state cell, query key, route, or branch generation;
- lifecycle journal counts;
- barrier hook and component path;
- live candidate and candidate-owned resource counts.

Never expose state values or query data in diagnostics by default.

## Open questions

1. Should all active-branch changes invalidate a candidate initially, or only versions in its read set?
2. Are setup/init resource changes always barriers, or should Pulse add a transactional resource hook with explicit prepare/commit/abort?
3. Should a fresh candidate be allowed to start cache-owned fetches before commit?
4. Does commit publish transport output before or after query observer activation? Ref routing must precede send.
5. Should unkeyed queries receive stable internal keys or remain branch-local?
6. What resource and time limits apply per session and mount?
7. Can custom hooks declare immutable/shareable state in addition to full fork adapters?
8. Should urgent active writes always invalidate a candidate first, or support fine-grained Solid-style rebase from the start?

## Recommended first experiment

Build Phase 1 plus `ReactiveTransaction` slots for signals and eager COW for reactive containers. Use conservative mount-generation conflicts, defer all effects/unmounts, preserve revision callback history, and treat queries, setup/init resources, refs, process-global state, and external writes as barriers.

That slice proves the central transaction—active render continues, candidate abort is invisible, candidate commit is atomic—before redesigning query ownership or optimizing copy-on-write behavior.
