# Pulse tutorial starter

This workspace contains a minimal Vite SSR shell used by the Pulse tutorial examples. It focuses on loading Pulse view definitions without extra tooling or deployment scaffolding.

## What's included
- Vite dev server for client assets
- Bun SSR server for rendering
- Tailwind CSS via `@tailwindcss/vite`
- Pulse UI client mounting through the `app/` alias

## Setup

Install dependencies:

```bash
npm install
```

Start the development servers:

```bash
npm run dev
npm run ssr
```

Generate the production build:

```bash
npm run build
```

Refresh types when needed:

```bash
npm run typecheck
```
