# Known Issues

- Message ordering not guaranteed across global vs per-route queues on reconnect. Global messages (navigate_to, reload, api_call, channel_message) may flush before pending per-route updates/errors/js_exec. If strict cross-type ordering is required, use explicit sequencing or avoid reliance on ordering across queues.
- `examples/recharts.py` fails at startup: `pulse_recharts` declares a JS dependency on the npm package `pulse-recharts`, which is not published (404), so the web dependency install fails. Publish the JS package or add workspace-local resolution.
- SSR'd controlled form inputs can lose user edits typed during the hydration window: React restores the initial value when it hydrates, and subsequent keystrokes append to it. Inherent to SSR + controlled inputs; mitigations would be uncontrolled mode or hydration-aware inputs.
