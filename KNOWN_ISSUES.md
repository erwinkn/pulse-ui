# Known Issues

- Message ordering not guaranteed across global vs per-route queues on reconnect. Global messages (navigation, reloads, API calls, and channel traffic) may flush before pending per-route updates, errors, or JavaScript execution. If strict cross-type ordering is required, use explicit sequencing or avoid reliance on ordering across queues.
