from __future__ import annotations

import sys

PREFIX = "\x00pulse:"
WORKER_READY = "worker-ready"
VITE_CONFIGURED = "vite-configured"
VITE_LISTENING = "vite-listening"

MESSAGES = frozenset({WORKER_READY, VITE_CONFIGURED, VITE_LISTENING})


def emit(message: str) -> None:
	if message not in MESSAGES:
		raise ValueError(f"Unknown protocol message: {message}")
	sys.stdout.write(f"\n{PREFIX}{message}\n")
	sys.stdout.flush()


def parse(line: str) -> tuple[str | None, str]:
	index = line.find(PREFIX)
	if index < 0:
		return None, line

	start = index + len(PREFIX)
	for message in MESSAGES:
		if line.startswith(message, start):
			end = start + len(message)
			return message, line[:index] + line[end:]
	return None, line
