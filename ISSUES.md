# Deferred issues

These issues were identified during the single-origin architecture review and intentionally excluded from that migration. Unless noted otherwise, they are pre-existing problems rather than regressions caused by the single-origin work.

## Render affinity and directives

Status: deferred architecture work.

Pulse deployment plugins currently carry provider affinity through prerender and Socket.IO directives. Native `PulseForm` submissions cannot reliably apply that affinity without parsing and rewriting arbitrary action URLs in the browser. The attempted client-side rewriting was removed.

Design the complete cross-provider routing contract before changing this again:

- Define one render identity and the transports that carry it for loaders, API calls, Socket.IO, and native forms.
- Keep provider routing in deployment packages rather than Pulse application code.
- Define stale-render behavior when its deployment no longer exists.
- Prove the design works for both Railway's programmable router and AWS infrastructure.
- Remove obsolete deployment directives only as part of the complete migration.

Do not restore form-specific URL rewriting as an isolated fix.

## Socket.IO reconnects ignore refreshed directives

The Socket.IO client passes `directives.socketio.auth`/`query` to `io(...)` only when the socket is created. `setDirectives` updates the stored directives, but socket.io's automatic reconnection reuses the options from creation, so a reconnect after a new prerender still carries the original affinity query until a full page load.

Resolve this as part of the affinity redesign above: either recreate the socket when directives change, or supply auth/query via callables so reconnects read current values.

## Prod server regenerates codegen output at boot

In prod with a web process (`pulse run --prod` without `--backend-only`), `asgi_factory` reruns codegen at every uvicorn startup. The web bundle was already built from files generated at image build time, so the runtime regeneration cannot affect the served app; it only costs startup time and requires a writable web root (breaks read-only container filesystems).

Decide when codegen runs in prod — likely never at runtime when serving a prebuilt bundle — and make the CLI set `PULSE_DISABLE_CODEGEN` accordingly.

## Rename stale Socket.IO log labels

`packages/pulse/js/src/client.tsx` still logs with the `[SocketIOTransport]` prefix. The `SocketIOTransport` class was deleted in the single-origin migration; the logs belong to `PulseSocketIOClient`. Rename the prefixes.

## Structurally reserve `/_pulse`

Pulse route objects reject paths under `/_pulse`, but routes registered directly on the underlying FastAPI app can still shadow framework endpoints.

Required outcome:

- Framework HTTP and WebSocket endpoints have a routing boundary that user FastAPI routes and catch-all proxies cannot shadow.
- Unknown `/_pulse/*` paths stay inside the framework namespace.
- Framework paths are defined centrally instead of repeated as string literals.
- User routes outside the namespace remain unaffected.

## Stream the Railway router proxy

The affinity router buffers full request and response bodies in memory (`await request.body()` / `await response.read()`) and rebuilds response headers through a dict, which collapses duplicate headers — multiple `Set-Cookie` headers from a backend are dropped. A streaming rewrite (chunked request/response passthrough, raw-header preservation, upstream release on client disconnect) was implemented during the single-origin migration and reverted as out-of-scope.

Reintroduce it as standalone work:

- Stream request and response bodies without buffering.
- Preserve duplicate request and response headers (notably `Set-Cookie`).
- Release the upstream connection when the client disconnects mid-stream.
- Cover all of the above with tests, including large-body and disconnect cases.

## Remove unused credentials from the Railway router service

The router service is provisioned with `RAILWAY_TOKEN` and `PULSE_RAILWAY_INTERNAL_TOKEN`, but the router runtime reads neither: `AffinityRouter.internal_token` has no usage sites, and `RAILWAY_TOKEN` is only consumed by CLI-side deploy tooling. A public-facing service holds a project token it does not need. A removal was implemented during the single-origin migration and reverted because it only covered new stacks.

Do this as standalone work, and make it complete:

- Stop provisioning both variables on new router services and delete the dead `internal_token` plumbing.
- During reconciliation, explicitly delete the retired variables from existing router services (`configure_service_if_changed` compares only desired keys and upserts with `replace=False`, so unlisted variables survive otherwise).
- Update stack inspection so upgraded and freshly scaffolded stacks both validate.

## Deduplicate Railway deployment finalization

Railway image and source deployments duplicate the register, routed-health verification, promotion, public verification, and result-construction sequence in `deployment.py`.

Extract one behavior-preserving finalization flow shared by both deployment modes. Keep build and service-preparation differences outside it. Do not combine this cleanup with the deferred affinity redesign.

## Make the API-call credentials contract explicit

The Python and TypeScript message contracts require `credentials`, while the JavaScript client still accepts an omitted value through a fallback. Tests currently exercise the omitted case.

Choose and enforce one contract across both runtimes:

- If required, always emit the field and consume it directly without a fallback.
- If optional, mark it optional in both schemas and document the default.
- Cover every supported credentials mode with wire-level tests.

Do not retain required types and optional runtime behavior simultaneously.

## Give MSAL URLs one owner

The MSAL package exposes a login helper, but examples and documentation manually build login URLs and interpolate `next`. Route-prefix normalization and endpoint construction are also duplicated.

Provide one canonical login/callback URL builder that:

- owns route-prefix normalization;
- encodes `next` as one query value;
- stays consistent with the routes registered by `MSALPlugin`;
- preserves the same-origin redirect validation already enforced by the plugin;
- is used by package examples and documentation.
