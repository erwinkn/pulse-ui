# Known Issues

- Message ordering not guaranteed across global vs per-route queues on reconnect. Global messages (navigate_to, reload, api_call, channel_message) may flush before pending per-route updates/errors/js_exec. If strict cross-type ordering is required, use explicit sequencing or avoid reliance on ordering across queues.
- Inputs the user edits before hydration are restored by the pre-hydration capture script (recorded in the SSR document, replayed through React after the hydration commit). Caveat: inputs inside lazy/suspended subtrees that hydrate after the root commit can still lose pre-hydration edits.
