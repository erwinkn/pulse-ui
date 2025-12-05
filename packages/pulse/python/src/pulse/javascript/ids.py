"""Unique ID generator for JavaScript codegen."""

from itertools import count

_counter = count(1)


def generate_id() -> str:
	"""Generate unique hex ID like '1', '2', 'a', 'ff', etc."""
	return f"{next(_counter):x}"


def reset_id_counter() -> None:
	"""Reset counter (for testing)."""
	global _counter
	_counter = count(1)
