# Code Splitting + SSR Proof of Concept

Validate that per-route code splitting works with unified VDOM rendering before implementing in Pulse.

## Goals

1. Verify Vite creates separate chunks for dynamically imported route modules
2. Verify Bun SSR can import route modules and render unified VDOM
3. Verify client can load chunks on-demand and hydrate
4. Verify prefetching works (preload chunks before navigation)

## Project Structure

```
poc/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── entry-client.tsx      # Client entry, hydration
│   ├── entry-server.tsx      # SSR render function (used by Bun)
│   ├── app.tsx               # Main app component
│   ├── vdom-renderer.tsx     # Simple VDOM → React renderer
│   ├── router/
│   │   ├── match.ts          # Route matching
│   │   ├── loader.ts         # Dynamic chunk loading
│   │   └── prefetch.ts       # Prefetch on hover/viewport
│   ├── routes/
│   │   ├── index.ts          # Route manifest (dynamic imports)
│   │   ├── home.tsx          # Home route registry
│   │   ├── dashboard.tsx     # Dashboard route registry
│   │   └── settings.tsx      # Settings route registry
│   └── components/           # Test components (one per route to verify splitting)
│       ├── home-widget.tsx
│       ├── dashboard-chart.tsx
│       └── settings-form.tsx
├── server/
│   └── ssr.ts                # Bun SSR server
└── test/
    ├── bundle-analysis.ts    # Verify chunks are separate
    └── e2e.spec.ts           # E2E navigation test
```

## Implementation Steps

### Step 1: Project Setup

Create minimal Vite + React + TypeScript project with Bun using the Vite CLI.

```bash
bun create vite poc --template react-ts
cd poc
bun install
```

Then modify the generated vite.config.ts to enable manifest generation:

**vite.config.ts:**
```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        client: 'src/entry-client.tsx',
      },
    },
    manifest: true,
    ssrManifest: true,
  },
  ssr: {
    noExternal: ['react', 'react-dom'],
  },
});
```

### Step 2: Route Registry Pattern

Each route file exports a registry of components it uses. This is the key pattern to validate.

**src/routes/home.tsx:**
```tsx
import { HomeWidget } from '../components/home-widget';

// Each route exports its component registry
export const registry = {
  'HomeWidget': HomeWidget,
};

export const path = '/';
```

**src/routes/dashboard.tsx:**
```tsx
import { DashboardChart } from '../components/dashboard-chart';

export const registry = {
  'DashboardChart': DashboardChart,
};

export const path = '/dashboard';
```

**src/routes/settings.tsx:**
```tsx
import { SettingsForm } from '../components/settings-form';

export const registry = {
  'SettingsForm': SettingsForm,
};

export const path = '/settings';
```

### Step 3: Route Manifest with Dynamic Imports

**src/routes/index.ts:**
```tsx
// This file maps route patterns to dynamic imports
// Vite will code-split each import() target into separate chunks

export type RouteModule = {
  registry: Record<string, React.ComponentType<any>>;
  path: string;
};

export const routeLoaders: Record<string, () => Promise<RouteModule>> = {
  '/': () => import('./home'),
  '/dashboard': () => import('./dashboard'),
  '/settings': () => import('./settings'),
};

// For SSR: synchronous imports (Bun bundles these)
export const ssrRouteLoaders: Record<string, () => RouteModule> = {
  '/': () => require('./home'),
  '/dashboard': () => require('./dashboard'),
  '/settings': () => require('./settings'),
};
```

### Step 4: Simple VDOM Renderer

Simplified version of Pulse's VDOM rendering. The key is that it uses a registry to resolve component references.

**src/vdom-renderer.tsx:**
```tsx
import React from 'react';

// Simplified VDOM node structure
export type VdomNode =
  | string
  | number
  | null
  | { type: string; props: Record<string, any>; children: VdomNode[] };

type Registry = Record<string, React.ComponentType<any>>;

export function renderVdom(node: VdomNode, registry: Registry): React.ReactNode {
  if (node === null || typeof node === 'string' || typeof node === 'number') {
    return node;
  }

  const { type, props, children } = node;

  // Look up component in registry, fall back to HTML element
  const Component = registry[type] || type;

  const renderedChildren = children.map((child, i) => (
    <React.Fragment key={i}>{renderVdom(child, registry)}</React.Fragment>
  ));

  return <Component {...props}>{renderedChildren}</Component>;
}
```

### Step 5: Route Matching

**src/router/match.ts:**
```ts
// Simplified route matching (just exact match for POC)
export function matchRoute(pathname: string, patterns: string[]): string | null {
  // Exact match first
  if (patterns.includes(pathname)) {
    return pathname;
  }
  return null;
}
```

### Step 6: Dynamic Chunk Loader

**src/router/loader.ts:**
```tsx
import { routeLoaders, type RouteModule } from '../routes';

// Cache loaded modules
const loadedModules: Record<string, RouteModule> = {};

export async function loadRouteChunk(pattern: string): Promise<RouteModule> {
  if (loadedModules[pattern]) {
    return loadedModules[pattern];
  }

  const loader = routeLoaders[pattern];
  if (!loader) {
    throw new Error(`No loader for route: ${pattern}`);
  }

  const module = await loader();
  loadedModules[pattern] = module;
  return module;
}

export function getLoadedRegistry(): Record<string, React.ComponentType<any>> {
  const merged: Record<string, React.ComponentType<any>> = {};
  for (const mod of Object.values(loadedModules)) {
    Object.assign(merged, mod.registry);
  }
  return merged;
}
```

### Step 7: Prefetching

**src/router/prefetch.ts:**
```tsx
import { routeLoaders } from '../routes';

const prefetched = new Set<string>();

export function prefetchRoute(pattern: string): void {
  if (prefetched.has(pattern) || !routeLoaders[pattern]) {
    return;
  }
  prefetched.add(pattern);

  // Trigger dynamic import (Vite will load the chunk)
  routeLoaders[pattern]();
}

// Prefetch on hover
export function createHoverPrefetch(pattern: string) {
  return {
    onMouseEnter: () => prefetchRoute(pattern),
  };
}

// Prefetch when link enters viewport
export function usePrefetchOnViewport(pattern: string, ref: React.RefObject<HTMLElement>) {
  React.useEffect(() => {
    if (!ref.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          prefetchRoute(pattern);
          observer.disconnect();
        }
      },
      { rootMargin: '100px' }
    );

    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [pattern]);
}
```

### Step 8: Client Entry

**src/entry-client.tsx:**
```tsx
import React from 'react';
import { hydrateRoot, createRoot } from 'react-dom/client';
import { App } from './app';
import { loadRouteChunk, getLoadedRegistry } from './router/loader';
import { matchRoute } from './router/match';
import { routeLoaders } from './routes';

async function main() {
  const pathname = window.location.pathname;
  const pattern = matchRoute(pathname, Object.keys(routeLoaders));

  if (pattern) {
    // Load required chunk before hydration
    await loadRouteChunk(pattern);
  }

  const container = document.getElementById('root')!;
  const initialVdom = (window as any).__INITIAL_VDOM__;

  if (initialVdom) {
    // Hydrate SSR content
    hydrateRoot(
      container,
      <App initialVdom={initialVdom} initialRegistry={getLoadedRegistry()} />
    );
  } else {
    // Client-only render
    createRoot(container).render(
      <App initialVdom={null} initialRegistry={getLoadedRegistry()} />
    );
  }
}

main();
```

### Step 9: App Component

**src/app.tsx:**
```tsx
import React, { useState, useCallback } from 'react';
import { renderVdom, type VdomNode } from './vdom-renderer';
import { loadRouteChunk, getLoadedRegistry } from './router/loader';
import { matchRoute } from './router/match';
import { routeLoaders } from './routes';
import { createHoverPrefetch } from './router/prefetch';

type Props = {
  initialVdom: VdomNode | null;
  initialRegistry: Record<string, React.ComponentType<any>>;
};

// Fake VDOM for each route (in real Pulse, this comes from Python)
const routeVdom: Record<string, VdomNode> = {
  '/': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Home'] },
      { type: 'HomeWidget', props: { title: 'Welcome' }, children: [] },
    ],
  },
  '/dashboard': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Dashboard'] },
      { type: 'DashboardChart', props: { data: [1, 2, 3] }, children: [] },
    ],
  },
  '/settings': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Settings'] },
      { type: 'SettingsForm', props: {}, children: [] },
    ],
  },
};

export function App({ initialVdom, initialRegistry }: Props) {
  const [vdom, setVdom] = useState<VdomNode | null>(initialVdom);
  const [registry, setRegistry] = useState(initialRegistry);
  const [loading, setLoading] = useState(false);

  const navigate = useCallback(async (pathname: string) => {
    setLoading(true);

    // 1. Match route
    const pattern = matchRoute(pathname, Object.keys(routeLoaders));
    if (!pattern) {
      setLoading(false);
      return;
    }

    // 2. Load chunk (this is the key - dynamic import for code splitting)
    await loadRouteChunk(pattern);

    // 3. Update registry with newly loaded components
    setRegistry(getLoadedRegistry());

    // 4. Get VDOM (in real Pulse, this comes from Python via WebSocket)
    const newVdom = routeVdom[pathname] || null;
    setVdom(newVdom);

    // 5. Update URL
    window.history.pushState({}, '', pathname);
    setLoading(false);
  }, []);

  return (
    <div>
      <nav>
        <a href="/" onClick={(e) => { e.preventDefault(); navigate('/'); }} {...createHoverPrefetch('/')}>
          Home
        </a>
        {' | '}
        <a href="/dashboard" onClick={(e) => { e.preventDefault(); navigate('/dashboard'); }} {...createHoverPrefetch('/dashboard')}>
          Dashboard
        </a>
        {' | '}
        <a href="/settings" onClick={(e) => { e.preventDefault(); navigate('/settings'); }} {...createHoverPrefetch('/settings')}>
          Settings
        </a>
      </nav>

      {loading && <div className="loading">Loading...</div>}

      <main>
        {vdom ? renderVdom(vdom, registry) : <p>No content</p>}
      </main>
    </div>
  );
}
```

### Step 10: Test Components

**src/components/home-widget.tsx:**
```tsx
import React from 'react';

// Large import to make chunk size visible
import { format } from 'date-fns';

export function HomeWidget({ title }: { title: string }) {
  return (
    <div className="home-widget">
      <h2>{title}</h2>
      <p>Today is {format(new Date(), 'PPPP')}</p>
    </div>
  );
}
```

**src/components/dashboard-chart.tsx:**
```tsx
import React from 'react';

// Different large import
import { chunk } from 'lodash-es';

export function DashboardChart({ data }: { data: number[] }) {
  const chunked = chunk(data, 2);
  return (
    <div className="dashboard-chart">
      <h2>Chart</h2>
      <pre>{JSON.stringify(chunked)}</pre>
    </div>
  );
}
```

**src/components/settings-form.tsx:**
```tsx
import React, { useState } from 'react';

// Another different import
import { z } from 'zod';

const schema = z.object({ name: z.string().min(1) });

export function SettingsForm() {
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const validate = () => {
    const result = schema.safeParse({ name });
    setError(result.success ? '' : 'Name required');
  };

  return (
    <div className="settings-form">
      <input value={name} onChange={(e) => setName(e.target.value)} onBlur={validate} />
      {error && <span className="error">{error}</span>}
    </div>
  );
}
```

### Step 11: Bun SSR Server

**server/ssr.ts:**
```tsx
import { renderToString } from 'react-dom/server';
import React from 'react';
import { renderVdom, type VdomNode } from '../src/vdom-renderer';

// For SSR, we need synchronous imports
// Bun bundles these at build time
const routeRegistries: Record<string, Record<string, React.ComponentType<any>>> = {
  '/': require('../src/routes/home').registry,
  '/dashboard': require('../src/routes/dashboard').registry,
  '/settings': require('../src/routes/settings').registry,
};

// Fake VDOM (same as client for POC)
const routeVdom: Record<string, VdomNode> = {
  '/': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Home'] },
      { type: 'HomeWidget', props: { title: 'Welcome' }, children: [] },
    ],
  },
  '/dashboard': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Dashboard'] },
      { type: 'DashboardChart', props: { data: [1, 2, 3] }, children: [] },
    ],
  },
  '/settings': {
    type: 'div',
    props: { className: 'page' },
    children: [
      { type: 'h1', props: {}, children: ['Settings'] },
      { type: 'SettingsForm', props: {}, children: [] },
    ],
  },
};

const server = Bun.serve({
  port: 3001,
  async fetch(req) {
    const url = new URL(req.url);

    if (req.method === 'POST' && url.pathname === '/render') {
      const { pathname } = await req.json();

      const registry = routeRegistries[pathname] || {};
      const vdom = routeVdom[pathname];

      if (!vdom) {
        return new Response('Not found', { status: 404 });
      }

      // Render VDOM to HTML using registry
      const content = renderToString(
        <>{renderVdom(vdom, registry)}</>
      );

      return Response.json({ html: content, vdom });
    }

    return new Response('Not found', { status: 404 });
  },
});

console.log(`SSR server running on http://localhost:${server.port}`);
```

### Step 12: HTML Template

**index.html:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Splitting POC</title>
</head>
<body>
  <div id="root"><!--ssr-outlet--></div>
  <script>
    window.__INITIAL_VDOM__ = /*vdom-placeholder*/null/*vdom-placeholder*/;
  </script>
  <script type="module" src="/src/entry-client.tsx"></script>
</body>
</html>
```

### Step 13: Bundle Analysis Test

**test/bundle-analysis.ts:**
```ts
import { readdir, stat } from 'fs/promises';
import { join } from 'path';

async function analyzeBundle() {
  const distDir = './dist/assets';
  const files = await readdir(distDir);

  const jsFiles = files.filter(f => f.endsWith('.js'));

  console.log('\n=== Bundle Analysis ===\n');

  for (const file of jsFiles) {
    const { size } = await stat(join(distDir, file));
    console.log(`${file}: ${(size / 1024).toFixed(2)} KB`);
  }

  // Verify we have multiple chunks (not just one bundle)
  if (jsFiles.length < 3) {
    console.error('\n❌ FAIL: Expected multiple chunks, got', jsFiles.length);
    process.exit(1);
  }

  console.log('\n✅ PASS: Multiple chunks created (code splitting works)\n');
}

analyzeBundle();
```

## Validation Checklist

After implementation, verify:

- [ ] `bun run build` creates multiple JS chunks in `dist/assets/`
- [ ] Each route's dependencies (date-fns, lodash-es, zod) are in separate chunks
- [ ] Initial page load only fetches the chunk for current route
- [ ] Navigating to another route triggers dynamic import (visible in Network tab)
- [ ] Hovering over links prefetches chunks (visible in Network tab)
- [ ] SSR server renders correct HTML for each route
- [ ] Client hydrates without mismatch warnings
- [ ] Build analysis shows clear separation of route code

## Success Criteria

1. **Code Splitting:** `dist/assets/` contains separate chunks:
   - `home-[hash].js` (includes date-fns)
   - `dashboard-[hash].js` (includes lodash-es)
   - `settings-[hash].js` (includes zod)
   - `entry-client-[hash].js` (shared code)

2. **SSR Works:** `curl -X POST http://localhost:3001/render -d '{"pathname":"/"}' -H 'Content-Type: application/json'` returns rendered HTML

3. **Client Hydration:** No React hydration warnings in console

4. **Dynamic Loading:** Network tab shows chunks loaded on-demand during navigation

5. **Prefetching:** Network tab shows chunks loaded on hover before click

## Implementation Order

1. Create project structure and config files
2. Implement route files with registries
3. Implement VDOM renderer
4. Implement route matching and loading
5. Implement client entry and app
6. Implement SSR server
7. Test build output (bundle analysis)
8. Test SSR rendering
9. Test client navigation
10. Test prefetching

## Notes

- This POC uses hardcoded VDOM; real Pulse gets VDOM from Python
- POC uses exact path matching; real implementation needs full pattern matching
- POC doesn't handle nested routes/layouts; that's tested separately
- Focus is on validating the bundling/loading architecture
