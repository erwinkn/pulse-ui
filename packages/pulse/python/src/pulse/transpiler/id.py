"""Shared ID generator for unique identifiers across imports, functions, constants."""

from __future__ import annotations

_id_counter: int = 0


def next_id() -> str:
	"""Generate a unique ID for imports, functions, or constants."""
	global _id_counter
	_id_counter += 1
	return str(_id_counter)


def reset_id_counter() -> None:
	"""Reset the shared ID counter. Called by clear_* functions."""
	global _id_counter
	_id_counter = 0
