# Pulse Mantine + Vite example

This project shows how to host Pulse UI alongside the Mantine component registry inside a minimal Vite SSR app. It keeps the tooling surface small so you can focus on wiring Pulse into your own Mantine projects.

## What's included
- Vite dev server for client assets
- Bun SSR server for rendering
- Mantine core, dates, charts, and notifications packages
- Pulse component loading through the `/app` alias

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

Create a production build:

```bash
npm run build
```

Refresh generated types when needed:

```bash
npm run typecheck
```
