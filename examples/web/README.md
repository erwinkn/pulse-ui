# Pulse web example

The web project for the Pulse examples in this directory. It hosts the
generated Pulse app (`app/pulse/`, written by codegen) on top of a plain Vite +
React setup with the custom Pulse router — no third-party routing framework.

## What's included
- Vite dev server for assets and HMR (`bun run dev`)
- A small Bun SSR server (`server/ssr.ts`) that renders HTML for the Python
  server (`bun run ssr`)
- Tailwind CSS via `@tailwindcss/vite`
- Client/server entries in `src/entry-client.tsx` and `src/entry-server.tsx`

## Usage

You normally don't run this project directly — `pulse run ../main.py` starts
the Python server, the Vite asset server, and the SSR server together.

To build for production:

```bash
bun run build   # vite build && vite build --ssr src/entry-server.tsx
```
