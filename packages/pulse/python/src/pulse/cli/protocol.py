from __future__ import annotations

import contextlib
import sys

PREFIX = "\x00pulse:"
WORKER_READY = "worker-ready"
VITE_CONFIGURED = "vite-configured"
VITE_LISTENING = "vite-listening"

MESSAGES = frozenset({WORKER_READY, VITE_CONFIGURED, VITE_LISTENING})
MARKER_TOKEN_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def emit(message: str) -> None:
	if message not in MESSAGES:
		raise ValueError(f"Unknown protocol message: {message}")
	# Signaling must never take the child down when the supervisor is gone
	# (closed pipe); the stdin watchdog handles that shutdown.
	with contextlib.suppress(OSError):
		sys.stdout.write(f"{PREFIX}{message}\n")
		sys.stdout.flush()


def parse(line: str) -> tuple[list[str], str]:
	"""Extract every protocol marker from a line of child output.

	Returns the markers found plus the line with them stripped.
	"""
	messages: list[str] = []
	search_from = 0
	while True:
		index = line.find(PREFIX, search_from)
		if index < 0:
			return messages, line
		start = index + len(PREFIX)
		for message in MESSAGES:
			if line.startswith(message, start):
				end = start + len(message)
				if (
					message == WORKER_READY
					and end < len(line)
					and line[end] in MARKER_TOKEN_CHARACTERS
				):
					continue
				messages.append(message)
				line = line[:index] + line[end:]
				search_from = index
				break
		else:
			search_from = index + len(PREFIX)
