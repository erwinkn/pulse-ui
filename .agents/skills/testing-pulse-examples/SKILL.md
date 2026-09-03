---
name: testing-pulse-examples
description: How to run and browser-test a Pulse example app end-to-end (dev server, single-instance lock, first-load 504, which examples exercise timers/queries/routes, how to scan server logs for event-loop errors).
---

# Browser-testing Pulse example apps

## Start a dev server

```bash
# run this in a PERSISTENT shell (a one-shot `nohup ... &` has silently produced no log file)
cd <repo root>
uv run pulse run examples/main.py --port 8000 --interrupt --plain --verbose 2>&1 | tee /tmp/pulse.log
```

- Startup takes ~30-45s (bun install + vite dev + route codegen). Wait for `Ready: http://localhost:<port>` in the log.
- `bun run build` must have run at least once (`make sync` does it); vite.config.ts imports `pulse-ui-client/dist`.
- **Only one Pulse dev instance per web root**: the lock lives in `examples/web/.pulse*`. Starting a second example while one runs fails with
  `Error: Another Pulse dev instance is running at http://localhost:8000 (pid=...)`.
  Use `--interrupt` to stop the previous one and start the new app. Plan multi-app testing as sequential phases (one recording per app) rather than two servers.
- With `--interrupt` the new server may land on a different port (e.g. 8001) — always re-read `Ready:` from the log instead of assuming the port.
- Passing `--port N --no-find-port` still works, but check the log; `--find-port` is the default.

## First page load can 504

The first load after startup often 504s on `/node_modules/.vite/deps/*` while vite prebundles, which leaves the page rendered but **not hydrated** (clicks do nothing, no websocket). Reload once (F5) and hydration works. Don't report this as a bug — verify with a reload before concluding a callback is broken.

## Which examples exercise what

- `examples/main.py` — multi-route (`/`, `/counter` + nested `/counter/details`, `/query`, `/async-effect`, `/components`, `/dynamic/...`), layout-level shared counter (fastest hydration check: click "Increment Shared"), sync + async callbacks, a self-rescheduling async ticking task (`Start ticking` / `Stop ticking`), a lazy async effect (`/async-effect`), keyed + unkeyed queries (`/query`).
  Note: the "Session Context" block on `/` only renders when a middleware populates `connected_at`/`ip`; `LoggingMiddleware` is commented out, so its absence is expected.
- `examples/query.py` — best app for time-driven scheduling: interval observers with `refetch_interval=0.5` / `1.5` and visible `calls=N` counters, plus mutations, retries, stale_time. Toggling "Disable fast (0.5s)" proves cancellation without killing the other cadence.
- `examples/infinite_query.py` — same interval pattern for infinite queries.
- `examples/refs.py` — imperative ref round-trips (`Focus`, `Set value`, `Get value`, `Trigger click`, `Set text`, `Get text`, `Scroll to target`, `Measure target`). Each action appends to the on-page "Event log" with a concrete result — a good check that awaited scheduled work resolves instead of hanging on its timeout guard.
- `examples/forms.py` — auto-managed and manually managed form submits; a JSON payload entry appears under "Auto form submissions" / "Manual form submissions" and "Is submitting" returns to False.
- `examples/debounced.py` — exercises `pulse.scheduling.later` through `ps.debounced(handler, 2000)`. Two assertions worth doing: (1) type ~5 chars fast in each input → "Immediate" Callback count = 5 while "Debounced" = 1 after the pause; (2) type, then click "Toggle input (unmount)" within 2s → panel shows "Input unmounted..." and the debounced count/value must NOT change (proves the pending `later` task is cancelled with the component).

## Scanning for event-loop / scheduling regressions

Server-side loop bugs often don't show in the UI. After each flow:

```bash
# loop-binding era patterns plus the anyio-Scheduler era patterns
grep -niE "RuntimeError|cannot schedule|event loop is not running|different event loop|no bound event loop|Task was destroyed|Task exception was never retrieved|unhandled errors in a TaskGroup|CancelledError|Traceback" /tmp/pulse.log | grep -v "\[web\]"
```

Since scheduling moved to anyio task groups (`Scheduler` in `pulse/scheduling.py`), the failure strings to expect are `cannot schedule on <owner>: scheduler is not running` and `cannot schedule on <owner> from a thread running a different event loop`. Owners are `app` and `render:<id>`.

- `[web]`-prefixed lines are the React Router/vite process. A stale browser tab pointed at a route that the newly started app doesn't define logs `No routes matched location "/..."` there — harmless.
- Effect `print()` output (e.g. `Counter 1: Count is now N`) is a good liveness signal: tail the log to confirm a timer/task is still firing.
- Default `session_timeout` is 60s: after closing a tab, a still-running background task in that render session keeps ticking in the log for up to ~60s before cleanup. That is expected, not a leak.
- Proving idle cleanup fired without relying on log level: start the ticking task in TWO tabs, close one, keep the server alive >60s, then diff the interleaved `Counter 1 count: N` series — e.g.
  `grep "Counter 1 count:" /tmp/pulse.log | awk -F': ' '{print $2}' | awk 'NR>1 && $1<prev {print NR": "prev" -> "$1} {prev=$1}'`
  shows where the two series interleave and where the orphaned one stops while the live one continues. `logger.info("RenderSession ... expired after 60.0s timeout")` (app.py) did NOT appear in `--plain --verbose` output, so don't rely on grepping for it.

## Capturing clean-shutdown evidence (Ctrl-C)

SIGINT'ing the `pulse run` CLI kills the log pipeline before uvicorn's shutdown lines are written, so you only get *absence* of errors. To capture positive evidence, SIGINT the inner uvicorn process instead and let the CLI keep writing:

```bash
pgrep -f "m uvicorn <example>:app"      # e.g. "m uvicorn query:app"
kill -INT <that pid>                    # CLI stays alive, so its stdout keeps flowing to the log
tail -12 /tmp/pulse.log                 # expect: Shutting down / Application shutdown complete / Finished server process
```

Expect exit within ~1-2s and no cancellation traceback or `ExceptionGroup`. A >20s hang is a failure.

## Testing the threadpool → serving-loop path (`Scheduler.post`)

No example ships a synchronous endpoint, so add one temporarily (report it, never commit it; revert with `git checkout -- examples/main.py`). A plain `def` FastAPI endpoint runs in Starlette's threadpool, so a reactive write inside it must reach the serving loop via `Scheduler.post`:

```python
class SyncBumpState(ps.State):
    bumps: int = 0
    last_thread: str = ""

_sync_bump_state = SyncBumpState()

# ...render f"bumps: {_sync_bump_state.bumps} ({_sync_bump_state.last_thread})" in a component...

@app.fastapi.get("/api/sync-bump")   # plain def, NOT async def
def api_sync_bump():
    import threading
    _sync_bump_state.bumps += 1
    _sync_bump_state.last_thread = threading.current_thread().name
    return {"bumps": _sync_bump_state.bumps, "thread": _sync_bump_state.last_thread}
```

Keep the rendering page open in tab 1, hit the endpoint from tab 2, and switch back **without reloading**: the count must update live and the thread name must be a worker thread (`asyncio_<n>` / `AnyIO worker thread`), never the main loop thread. Failure looks like a frozen number in tab 1 or `cannot schedule on app from outside its event loop` / `Unhandled exception in post(...)` in the log.
