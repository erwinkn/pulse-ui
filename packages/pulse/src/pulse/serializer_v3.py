"""Pulse serializer v3 implementation (Python).

The format mirrors the TypeScript implementation in ``packages/pulse-ui-client``.

Serialized payload structure::

    (
        ([refs, dates, sets, maps], payload),
    )

- ``refs``  – list of paths where the stored value is a reference to another
  object in the tree; the value at that position is the target object's path.
- ``dates`` – list of paths that should be materialised as ``datetime`` objects,
  the payload entry is the millisecond timestamp since the Unix epoch (UTC).
- ``sets``  – list of paths that are ``set`` instances; payload is an array of
  their items.
- ``maps``  – list of paths that are ``Map`` instances; payload is an object
  mapping string keys to child payloads.

This serializer preserves shared references and cycles across nested structures
containing primitives, lists/tuples, ``dict``/plain objects, ``set`` and ``Map``
instances, and ``datetime`` objects.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import datetime as dt
import types
from typing import Any

Primitive = int | float | str | bool | None
PlainJSON = Primitive | list["PlainJSON"] | dict[str, "PlainJSON"]
Serialized = tuple[tuple[list[str], list[str], list[str], list[str]], PlainJSON]

__all__ = [
    "serialize",
    "deserialize",
    "Serialized",
]


def serialize(data: Any) -> Serialized:
    seen: dict[int, str] = {}
    refs: list[str] = []
    dates: list[str] = []
    sets: list[str] = []
    maps: list[str] = []

    def process(value: Any, path: str) -> PlainJSON:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        obj_id = id(value)
        prev_ref = seen.get(obj_id)
        if prev_ref is not None:
            refs.append(path)
            return prev_ref
        seen[obj_id] = path

        if isinstance(value, dt.datetime):
            dates.append(path)
            return _datetime_to_millis(value)

        if isinstance(value, dict):
            result_dict: dict[str, PlainJSON] = {}
            for key, entry in value.items():
                key = str(key)
                result_dict[key] = process(entry, f"{path}.{key}")
            return result_dict

        if isinstance(value, (list, tuple)):
            result_list: list[PlainJSON] = []
            for index, entry in enumerate(value):
                result_list.append(process(entry, f"{path}.{index}"))
            return result_list

        if isinstance(value, set):
            items: list[PlainJSON] = []
            for index, entry in enumerate(value):
                items.append(process(entry, f"{path}.{index}"))
            sets.append(path)
            return items

        if is_dataclass(value):
            obj: dict[str, PlainJSON] = {}
            for f in fields(value):
                obj[f.name] = process(getattr(value, f.name), f"{path}.{f.name}")
            return obj

        if callable(value) or isinstance(value, (type, types.ModuleType)):
            raise TypeError(f"Unsupported value in serialization: {type(value)!r}")

        if hasattr(value, "__dict__"):
            obj = {}
            for key, entry in vars(value).items():
                if key.startswith("_"):
                    continue
                obj[key] = process(entry, f"{path}.{key}")
            return obj

        raise TypeError(f"Unsupported value in serialization: {type(value)!r}")

    payload = process(data, "")
    return ((refs, dates, sets, maps), payload)


def deserialize(
    payload: Serialized,
) -> Any:
    # Both JS Maps and records are reconstructed as dictionaries, so we don't
    # care about deserializing Maps
    (refs, dates, sets_paths, _), data = payload

    refs_set = set(refs)
    dates_set = set(dates)
    sets_set = set(sets_paths)

    objects: dict[str, Any] = {}

    def reconstruct(value: PlainJSON, path: str) -> Any:
        if path in refs_set:
            assert isinstance(value, str), "Reference payload must be a string path"
            assert value in objects, f"Dangling reference to {value!r}"
            return objects[value]

        if path in dates_set:
            assert isinstance(value, (int, float)), (
                "Date payload must be a numeric timestamp"
            )
            dt_value = _datetime_from_millis(value)
            objects[path] = dt_value
            return dt_value

        if value is None:
            return None

        if isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, list):
            if path in sets_set:
                result_set: set[Any] = set()
                objects[path] = result_set
                for index, entry in enumerate(value):
                    result_set.add(reconstruct(entry, f"{path}.{index}"))
                return result_set
            result_list: list[Any] = []
            objects[path] = result_list
            for index, entry in enumerate(value):
                result_list.append(reconstruct(entry, f"{path}.{index}"))
            return result_list

        if isinstance(value, dict):
            # Both maps and records are reconstructed as dictionaries
            result_dict: dict[str, Any] = {}
            objects[path] = result_dict
            for key, entry in value.items():
                result_dict[key] = reconstruct(entry, f"{path}.{key}")
            return result_dict

        raise TypeError(f"Unsupported value in deserialization: {type(value)!r}")

    return reconstruct(data, "")


def _datetime_to_millis(value: dt.datetime) -> int:
    if value.tzinfo is None:
        ts = value.replace(tzinfo=dt.timezone.utc).timestamp()
    else:
        ts = value.astimezone(dt.timezone.utc).timestamp()
    return int(round(ts * 1000))


def _datetime_from_millis(value: int | float) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc)
