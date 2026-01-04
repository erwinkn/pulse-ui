"""Pulse serializer v3 implementation (Python).

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
- ``dates`` – indices that should be materialised as ``datetime`` objects; the
  payload entry is the millisecond timestamp since the Unix epoch (UTC).
- ``sets``  – indices that are ``set`` instances; payload is an array of their
  items.
- ``maps``  – indices that are ``Map`` instances; payload is an object mapping
  string keys to child payloads. Python reconstructs these as ``dict``.

Nodes are assigned a single global index as they are visited (non-primitives
only). This preserves shared references and cycles across nested structures
containing primitives, lists/tuples, ``dict``/plain objects, ``set`` and
``datetime`` objects.
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
			return _datetime_to_millis(value)

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
			assert isinstance(value, (int, float)), (
				"Date payload must be a numeric timestamp"
			)
			dt_value = _datetime_from_millis(value)
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


def _datetime_to_millis(value: dt.datetime) -> int:
	if value.tzinfo is None:
		ts = value.replace(tzinfo=dt.UTC).timestamp()
	else:
		ts = value.astimezone(dt.UTC).timestamp()
	return int(round(ts * 1000))


def _datetime_from_millis(value: int | float) -> dt.datetime:
	return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.UTC)
