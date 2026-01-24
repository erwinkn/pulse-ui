# Pulse + Vite example

A minimal Vite application wired up to the Pulse UI client. It is intended as a reference for integrating Pulse into a custom SSR setup without React Router.

## What's included
- Vite dev server for client assets
- Bun SSR server for rendering
- Tailwind CSS via `@tailwindcss/vite`
- Pulse UI client components served from the `/app` alias

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

Generate a production build:

```bash
npm run build
```

Type definitions can be refreshed with:

```bash
npm run typecheck
```
