"""Pulse serializer v4 implementation (Python).

The format mirrors the TypeScript implementation in ``packages/pulse/js``.

Serialized payload structure::

    (
        ("refs|dates|sets|maps", payload),
    )

- The first element is a compact metadata string with four pipe-separated
  comma-separated integer lists representing global node indices for:
  ``refs``, ``dates``, ``sets``, ``maps``.
- ``refs``  – indices where the payload entry is an integer pointing to a
  previously visited node's index (shared refs/cycles).
- ``dates`` – indices that should be materialised as temporal objects; the
  payload entry is an ISO 8601 string:
  - ``YYYY-MM-DD`` → ``datetime.date``
  - ``YYYY-MM-DDTHH:MM:SS.SSSZ`` → ``datetime.datetime`` (UTC)
- ``sets``  – indices that are ``set`` instances; payload is an array of their
  items.
- ``maps``  – indices that are ``Map`` instances; payload is an object mapping
  string keys to child payloads. Python reconstructs these as ``dict``.

Nodes are assigned a single global index as they are visited (non-primitives
only). This preserves shared references and cycles across nested structures
containing primitives, lists/tuples, ``dict``/plain objects, ``set``, ``date``
and ``datetime`` objects.
"""

from __future__ import annotations

import datetime as dt
import math
import types
from dataclasses import fields, is_dataclass
from typing import Any

Primitive = int | float | str | bool | None
PlainJSON = Primitive | list["PlainJSON"] | dict[str, "PlainJSON"]
Serialized = tuple[tuple[list[int], list[int], list[int], list[int]], PlainJSON]

__all__ = [
	"serialize",
	"deserialize",
	"Serialized",
]


def serialize(data: Any) -> Serialized:
	"""Serialize a Python value to wire format.

	Converts Python values to a JSON-compatible format with metadata for
		preserving types like datetime, date, set, and shared references.

	Args:
		data: Value to serialize.

	Returns:
		Serialized tuple containing metadata and JSON payload.

	Raises:
		TypeError: For unsupported types (functions, modules, classes).
		ValueError: For Infinity float values.

	Supported types:
		- Primitives: None, bool, int, float, str
		- Collections: list, tuple, dict, set
		- datetime.datetime (converted to ISO 8601 UTC)
		- datetime.date (converted to ISO 8601 date string)
		- Dataclasses (serialized as dict of fields)
		- Objects with __dict__ (public attributes only)

	Notes:
		- NaN floats serialize as None
		- Infinity raises ValueError
		- Dict keys must be strings
		- Private attributes (starting with _) are excluded
		- Shared references and cycles are preserved

	Example:
		```python
		from datetime import datetime
		import pulse as ps

		data = {
			"name": "Alice",
			"created": datetime.now(),
			"tags": {"admin", "user"},
		}
		serialized = ps.serialize(data)
		```
	"""
	# Map object id -> assigned global index
	seen: dict[int, int] = {}
	refs: list[int] = []
	dates: list[int] = []
	sets: list[int] = []
	maps: list[int] = []

	global_index = 0

	def process(value: Any) -> PlainJSON:
		nonlocal global_index
		if value is None or isinstance(value, (bool, int, str)):
			return value
		if isinstance(value, float):
			if math.isnan(value):
				return None  # NaN → None (matches pandas None ↔ NaN semantics)
			if math.isinf(value):
				raise ValueError(
					f"Cannot serialize {value}: Infinity is not valid JSON. "
					+ "Replace with None or a sentinel value."
				)
			return value

		idx = global_index
		global_index += 1

		obj_id = id(value)
		prev_ref = seen.get(obj_id)
		if prev_ref is not None:
			refs.append(idx)
			return prev_ref
		seen[obj_id] = idx

		if isinstance(value, dt.datetime):
			dates.append(idx)
			return _datetime_to_iso(value)

		if isinstance(value, dt.date):
			dates.append(idx)
			return value.isoformat()

		if isinstance(value, dict):
			result_dict: dict[str, PlainJSON] = {}
			for key, entry in value.items():
				if not isinstance(key, str):
					raise TypeError(
						f"Dict keys must be strings, got {type(key).__name__}: {key!r}"  # pyright: ignore[reportUnknownArgumentType]
					)
				result_dict[key] = process(entry)
			return result_dict

		if isinstance(value, (list, tuple)):
			result_list: list[PlainJSON] = []
			for entry in value:
				result_list.append(process(entry))
			return result_list

		if isinstance(value, set):
			sets.append(idx)
			items: list[PlainJSON] = []
			for entry in value:
				items.append(process(entry))
			return items

		if is_dataclass(value):
			dc_obj: dict[str, PlainJSON] = {}
			for f in fields(value):
				dc_obj[f.name] = process(getattr(value, f.name))
			return dc_obj

		if callable(value) or isinstance(value, (type, types.ModuleType)):
			raise TypeError(f"Unsupported value in serialization: {type(value)!r}")

		if hasattr(value, "__dict__"):
			inst_obj: dict[str, PlainJSON] = {}
			for key, entry in vars(value).items():
				if key.startswith("_"):
					continue
				inst_obj[key] = process(entry)
			return inst_obj

		raise TypeError(f"Unsupported value in serialization: {type(value)!r}")

	payload = process(data)

	return ((refs, dates, sets, maps), payload)


def deserialize(
	payload: Serialized,
) -> Any:
	"""Deserialize wire format back to Python values.

	Reconstructs Python values from the serialized format, restoring
	date/datetime objects, sets, and shared references.

	Args:
		payload: Serialized tuple from serialize().

	Returns:
		Reconstructed Python value.

	Raises:
		TypeError: For malformed payloads.

	Notes:
		- datetime values are reconstructed as UTC-aware
		- date values are reconstructed as ``datetime.date``
		- set values are reconstructed as Python sets
		- Shared references and cycles are restored

	Example:
		```python
		from datetime import datetime
		import pulse as ps

		original = {"items": [1, 2, 3], "timestamp": datetime.now()}
		serialized = ps.serialize(original)
		restored = ps.deserialize(serialized)
		```
	"""
	(refs, dates, sets, _maps), data = payload
	refs = set(refs)
	dates = set(dates)
	sets = set(sets)
	# we don't care about maps

	objects: list[Any] = []

	def reconstruct(value: PlainJSON) -> Any:
		idx = len(objects)

		if idx in refs:
			assert isinstance(value, (int, float)), (
				"Reference payload must be numeric index"
			)
			# Placeholder to keep indices aligned
			objects.append(None)
			target_index = int(value)
			assert 0 <= target_index < len(objects), (
				f"Dangling reference to index {target_index}"
			)
			return objects[target_index]

		if idx in dates:
			assert isinstance(value, str), "Date payload must be an ISO string"
			if _is_date_literal(value):
				date_value = dt.date.fromisoformat(value)
				objects.append(date_value)
				return date_value
			dt_value = _datetime_from_iso(value)
			objects.append(dt_value)
			return dt_value

		if value is None:
			return None

		if isinstance(value, (bool, int, float, str)):
			return value

		if isinstance(value, list):
			if idx in sets:
				result_set: set[Any] = set()
				objects.append(result_set)
				for entry in value:
					result_set.add(reconstruct(entry))
				return result_set
			result_list: list[Any] = []
			objects.append(result_list)
			for entry in value:
				result_list.append(reconstruct(entry))
			return result_list

		if isinstance(value, dict):
			# Both maps and records are reconstructed as dictionaries in Python
			result_dict: dict[str, Any] = {}
			objects.append(result_dict)
			for key, entry in value.items():
				result_dict[str(key)] = reconstruct(entry)
			return result_dict

		raise TypeError(f"Unsupported value in deserialization: {type(value)!r}")

	return reconstruct(data)


def _datetime_to_iso(value: dt.datetime) -> str:
	if value.tzinfo is None:
		value = value.replace(tzinfo=dt.UTC)
	else:
		value = value.astimezone(dt.UTC)
	return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime_from_iso(value: str) -> dt.datetime:
	if value.endswith("Z"):
		value = value[:-1] + "+00:00"
	parsed = dt.datetime.fromisoformat(value)
	if parsed.tzinfo is None:
		return parsed.replace(tzinfo=dt.UTC)
	return parsed


def _is_date_literal(value: str) -> bool:
	return len(value) == 10 and value[4] == "-" and value[7] == "-"
