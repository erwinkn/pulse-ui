# Pulse AWS ECS web project

The web project for the AWS ECS deployment example. It hosts the generated
Pulse app (`app/pulse/`) on the standard Pulse web setup: Vite for assets and
client builds, and a Bun SSR server (`server/ssr.ts`) that renders HTML for
the Python server.

Build for production with `bun run build` (or `pulse build ../main.py`).
