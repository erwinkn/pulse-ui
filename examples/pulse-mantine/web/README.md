# Pulse Mantine web example

The web project for the Pulse Mantine examples. It hosts the generated Pulse
app (`app/pulse/`) on a plain Vite + React setup with the custom Pulse router,
and wraps the app in `MantineProvider` from the user-owned entry files
(`src/entry-client.tsx` / `src/entry-server.tsx`).

## What's included
- Mantine core, dates, and charts packages with the Pulse Mantine bridge
- Vite dev server for assets and HMR, plus a Bun SSR server (`server/ssr.ts`)
- PostCSS configured with `postcss-preset-mantine`

## Usage

Run any example via the Pulse CLI, e.g.:

```bash
uv run pulse run ../form.py
```
