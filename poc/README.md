# Code Splitting POC

POC for route-based code splitting with SSR support. Validates Vite chunks separate route dependencies.

## Quick Start

```bash
bun install
bun run build
bun run analyze
```

## Testing

### Goal 1: Vite creates separate chunks

```bash
bun run build && bun run analyze
```

Expected: 4 chunks (index, home, dashboard, settings), each containing only its route's dependencies.

### Goal 2: SSR renders correct HTML

```bash
bun run ssr &
sleep 2
curl -X POST http://localhost:3001/render -d '{"pathname":"/"}' -H 'Content-Type: application/json'
curl -X POST http://localhost:3001/render -d '{"pathname":"/dashboard"}' -H 'Content-Type: application/json'
curl -X POST http://localhost:3001/render -d '{"pathname":"/settings"}' -H 'Content-Type: application/json'
pkill -f "bun server/ssr.ts"
```

Expected: Each route returns JSON with `html` (rendered string) and `vdom` (for hydration).

### Goal 3: Client loads chunk before hydration

Review `src/entry-client.tsx`:
- Line 21: `await loadRouteChunk(pathname)` called BEFORE render
- Prevents hydration mismatch by ensuring component registry is populated

### Goal 4: Prefetch triggers dynamic import

Review `src/router/prefetch.ts`:
- `prefetchRoute()` calls `loader()` without await (line 23)
- Triggers dynamic import in background to warm chunk cache

### TypeScript

```bash
bunx tsc --noEmit
```

## Dev Server

```bash
bun run dev
```

Open http://localhost:5173. Navigate between /, /dashboard, /settings to test client-side routing.

## Architecture

```
src/
  routes/          # Route modules with registries
    index.ts       # routeLoaders (dynamic) + ssrRouteLoaders (sync)
    home.tsx       # HomeWidget + date-fns
    dashboard.tsx  # DashboardChart + lodash-es
    settings.tsx   # SettingsForm + zod
  router/
    loader.ts      # loadRouteChunk() with cache
    prefetch.ts    # prefetchRoute(), createHoverPrefetch(), usePrefetchOnViewport()
    match.ts       # matchRoute() utility
  components/      # Route-specific components with heavy deps
  app.tsx          # App with navigation, loads chunks on navigate
  entry-client.tsx # Client entry with hydration support
  vdom-renderer.tsx # VDOM to React renderer

server/
  ssr.ts           # Bun SSR server using require() for sync imports
```
