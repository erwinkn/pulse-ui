# Pulse Mantine + React Router example

This project shows how to host Pulse UI alongside the Mantine component registry inside a React Router app. It keeps the tooling surface small so you can focus on wiring Pulse into your own Mantine projects.

## What's included
- React Router SSR with `react-router-serve`
- Mantine core, dates, and charts packages with the Pulse Mantine bridge
- Pulse component loading through the `~/` alias

## Setup

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Create a production build:

```bash
npm run build
```

Refresh generated types when needed:

```bash
npm run typecheck
```
