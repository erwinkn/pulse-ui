"""Pulse serializer v5 marker codec.

Wire envelope:

    [5, wire_value]

Marker arrays:

    ["$", "a", wire_items]               # escaped plain array beginning "$"
    ["$", "d", "YYYY-MM-DD"]             # date
    ["$", "t", "YYYY-MM-DDTHH:MM:SS.mmmZ"]  # UTC datetime
    ["$", "m", [[string_key, wire_value], ...]]  # ordered map
    ["$", "s", [wire_value, ...]]        # unordered set
    ["$", "r", integer_id]               # identity reference
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from typing import Any, TypeAlias, cast

Primitive: TypeAlias = None | bool | int | float | str
WireValue: TypeAlias = Primitive | list["WireValue"] | dict[str, "WireValue"]
Serialized: TypeAlias = list[Any]

_MAX_SAFE_INTEGER = 2**53 - 1
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class WireMap(dict[str, Any]):
	"""Dict subclass that round-trips as a wire-level Map marker."""


__all__ = [
	"WireMap",
	"serialize",
	"deserialize",
	"Serialized",
]


def serialize(data: Any) -> Serialized:
	"""Serialize a Python value to the v5 wire format."""
	seen: dict[int, int] = {}

	def encode(value: Any, path: str) -> WireValue:
		scalar = _encode_scalar(value, path)
		if scalar is not _UNSET:
			return cast(Primitive, scalar)
		if callable(value):
			raise TypeError(
				f"Cannot serialize {path}: unsupported value of type "
				+ f"{type(value).__name__}."
			)

		if not _is_referenceable(value):
			raise TypeError(
				f"Cannot serialize {path}: unsupported value of type "
				+ f"{type(value).__name__}."
			)

		object_id = id(value)
		existing_id = seen.get(object_id)
		if existing_id is not None:
			return ["$", "r", existing_id]
		seen[object_id] = len(seen)

		if isinstance(value, dt.datetime):
			return ["$", "t", _datetime_to_wire(value, path)]
		elif isinstance(value, dt.date):
			return ["$", "d", dt.date.isoformat(value)]
		elif isinstance(value, WireMap):
			items: list[WireValue] = []
			seen_keys: set[str] = set()
			map_source = _copy_dict(cast(dict[object, Any], value))
			for raw_key, entry in map_source.items():
				if not isinstance(raw_key, str):
					raise TypeError(
						f"Cannot serialize {path}: map keys must be strings, got "
						+ f"{type(raw_key).__name__}."
					)
				key = str.__str__(raw_key)
				_validate_portable_string(key, path, "Cannot serialize")
				if key in seen_keys:
					raise ValueError(
						f"Cannot serialize {path}: duplicate map key {key!r}."
					)
				seen_keys.add(key)
				items.append([key, encode(entry, _path_key(path, key))])
			return ["$", "m", items]
		elif isinstance(value, dict):
			record_result: dict[str, WireValue] = {}
			entries: dict[str, Any] = {}
			record_source = _copy_dict(cast(dict[object, Any], value))
			for raw_key, entry in record_source.items():
				if not isinstance(raw_key, str):
					raise TypeError(
						f"Cannot serialize {path}: record keys must be strings, got "
						+ f"{type(raw_key).__name__}."
					)
				key = str.__str__(raw_key)
				_validate_portable_string(key, path, "Cannot serialize")
				if key in entries:
					raise ValueError(
						f"Cannot serialize {path}: duplicate record key {key!r}."
					)
				entries[key] = entry
			for key in _js_object_key_order(list(entries)):
				record_result[key] = encode(entries[key], _path_key(path, key))
			return record_result
		elif isinstance(value, (list, tuple)):
			sequence: Iterator[Any] = (
				cast(Iterator[Any], list.__iter__(value))
				if isinstance(value, list)
				else cast(Iterator[Any], tuple.__iter__(cast(tuple[Any, ...], value)))
			)
			items = [
				encode(entry, _path_index(path, index))
				for index, entry in enumerate(sequence)
			]
			if items and items[0] == "$":
				return ["$", "a", items]
			return items
		elif isinstance(value, set):
			items = [
				encode(entry, _path_index(path, index))
				for index, entry in enumerate(
					_sorted_set_items(cast(set[Any], value), path)
				)
			]
			return ["$", "s", items]
		elif _is_dataclass_instance(value):
			dataclass_result: dict[str, WireValue] = {}
			for field in fields(value):
				dataclass_result[field.name] = encode(
					object.__getattribute__(value, field.name),
					_path_key(path, field.name),
				)
			return dataclass_result
		elif hasattr(value, "__dict__"):
			object_result: dict[str, WireValue] = {}
			attributes = {
				key: entry
				for key, entry in cast(dict[str, Any], vars(value)).items()
				if not key.startswith("_")
			}
			for key in _js_object_key_order(list(attributes)):
				entry = attributes[key]
				object_result[key] = encode(entry, _path_key(path, key))
			return object_result
		else:
			raise TypeError(
				f"Cannot serialize {path}: unsupported value of type {type(value).__name__}."
			)

	return [5, encode(data, "$")]


def deserialize(payload: Serialized) -> Any:
	"""Deserialize a v5 wire payload back to Python values."""
	if not isinstance(payload, list):
		raise TypeError("Wire payload must be a two-item list: [5, wire_value].")
	envelope = _copy_list(payload)
	if len(envelope) != 2:
		raise TypeError("Wire payload must be a two-item list: [5, wire_value].")

	version, value = envelope
	version = _decode_scalar(version, "$<version>")
	if version != 5:
		raise ValueError(f"Unknown wire version: {version!r}")

	identities: list[Any] = []

	def register_identity(value: Any) -> Any:
		identities.append(value)
		return value

	def decode(wire_value: Any, path: str) -> Any:
		scalar = _decode_scalar(wire_value, path)
		if scalar is not _UNSET:
			return scalar

		if isinstance(wire_value, list):
			wire_list = _copy_list(cast(list[Any], wire_value))
			if (
				wire_list
				and isinstance(wire_list[0], str)
				and str.__str__(wire_list[0]) == "$"
			):
				return decode_marker(wire_list, path)
			return decode_array(wire_list, path)

		if isinstance(wire_value, dict):
			return decode_record(_copy_dict(cast(dict[object, Any], wire_value)), path)

		raise TypeError(
			f"Cannot deserialize {path}: unsupported wire value of type "
			+ f"{type(wire_value).__name__}."
		)

	def decode_marker(marker: list[Any], path: str) -> Any:
		if len(marker) < 2 or not isinstance(marker[1], str):
			raise ValueError(f'Malformed marker at {path}: expected ["$", tag, ...].')

		tag = str.__str__(marker[1])
		_validate_portable_string(tag, path, "Cannot deserialize")

		if tag == "a":
			if len(marker) != 3 or not isinstance(marker[2], list):
				raise ValueError(f"Malformed array marker at {path}.")
			items = _copy_list(cast(list[Any], marker[2]))
			if (
				not items
				or not isinstance(items[0], str)
				or str.__str__(items[0]) != "$"
			):
				raise ValueError(
					f"Malformed array marker at {path}: payload must begin with '$'."
				)
			return decode_array(items, path)

		if tag == "d":
			if len(marker) != 3 or not isinstance(marker[2], str):
				raise ValueError(f"Malformed date marker at {path}.")
			return register_identity(_date_from_wire(str.__str__(marker[2]), path))

		if tag == "t":
			if len(marker) != 3 or not isinstance(marker[2], str):
				raise ValueError(f"Malformed datetime marker at {path}.")
			return register_identity(_datetime_from_wire(str.__str__(marker[2]), path))

		if tag == "m":
			if len(marker) != 3 or not isinstance(marker[2], list):
				raise ValueError(f"Malformed map marker at {path}.")
			map_result = cast(WireMap, register_identity(WireMap()))
			seen_keys: set[str] = set()
			entries = _copy_list(cast(list[Any], marker[2]))
			for index, entry in enumerate(entries):
				entry_path = _path_index(path, index)
				if not isinstance(entry, list):
					raise ValueError(
						f"Malformed map entry at {entry_path}: expected [string_key, value]."
					)
				entry_list = _copy_list(cast(list[Any], entry))
				if len(entry_list) != 2 or not isinstance(entry_list[0], str):
					raise ValueError(
						f"Malformed map entry at {entry_path}: expected [string_key, value]."
					)
				key = str.__str__(entry_list[0])
				_validate_portable_string(key, entry_path, "Cannot deserialize")
				if key in seen_keys:
					raise ValueError(f"Duplicate map key at {entry_path}: {key!r}")
				seen_keys.add(key)
				map_result[key] = decode(entry_list[1], _path_key(path, key))
			return map_result

		if tag == "s":
			if len(marker) != 3 or not isinstance(marker[2], list):
				raise ValueError(f"Malformed set marker at {path}.")
			set_result = cast(set[Any], register_identity(set()))
			seen_js_keys: set[tuple[Any, ...]] = set()
			seen_python_keys: dict[tuple[Any, ...], tuple[Any, ...]] = {}
			previous_sort_key: tuple[Any, ...] | None = None
			entries = _copy_list(cast(list[Any], marker[2]))
			for index, entry in enumerate(entries):
				item_path = _path_index(path, index)
				item = decode(entry, item_path)
				_validate_decoded_set_item(item, item_path)
				sort_key = _set_sort_key(item)
				if previous_sort_key is not None and sort_key < previous_sort_key:
					raise ValueError(
						f"Set entries are not canonically ordered at {item_path}."
					)
				previous_sort_key = sort_key
				js_key = _set_js_key(item)
				if js_key in seen_js_keys:
					raise ValueError(f"Duplicate set entry at {item_path}.")
				python_key = _set_python_key(item)
				existing_js_key = seen_python_keys.get(python_key)
				if existing_js_key is not None:
					raise ValueError(
						f"Set entry at {item_path} collides under Python equality."
					)
				seen_js_keys.add(js_key)
				seen_python_keys[python_key] = js_key
				set_result.add(item)
			return set_result

		if tag == "r":
			if len(marker) != 3:
				raise ValueError(f"Malformed reference marker at {path}.")
			identity_id = _decode_identity_id(marker[2], path)
			if identity_id >= len(identities):
				raise ValueError(f"Dangling reference at {path}: {identity_id}")
			return identities[identity_id]

		raise ValueError(f"Unknown wire marker tag at {path}: {tag!r}")

	def decode_array(entries: list[Any], path: str) -> list[Any]:
		result = cast(list[Any], register_identity([]))
		for index, entry in enumerate(entries):
			result.append(decode(entry, _path_index(path, index)))
		return result

	def decode_record(entries: dict[object, Any], path: str) -> dict[str, Any]:
		result = cast(dict[str, Any], register_identity({}))
		normalized_entries: dict[str, Any] = {}
		for raw_key, entry in entries.items():
			if not isinstance(raw_key, str):
				raise ValueError(
					f"Malformed record at {path}: keys must be strings, got "
					+ f"{type(raw_key).__name__}."
				)
			key = str.__str__(raw_key)
			_validate_portable_string(key, path, "Cannot deserialize")
			if key in normalized_entries:
				raise ValueError(f"Duplicate record key at {path}: {key!r}")
			normalized_entries[key] = entry
		for key in _js_object_key_order(list(normalized_entries)):
			result[key] = decode(normalized_entries[key], _path_key(path, key))
		return result

	return decode(value, "$")


class _Unset:
	pass


_UNSET = _Unset()


def _copy_list(value: list[Any]) -> list[Any]:
	return list.copy(value)


def _copy_dict(value: dict[object, Any]) -> dict[object, Any]:
	return dict.copy(value)


def _encode_scalar(value: Any, path: str) -> Primitive | _Unset:
	if value is None or isinstance(value, bool):
		return value
	if isinstance(value, str):
		normalized = str.__str__(value)
		_validate_portable_string(normalized, path, "Cannot serialize")
		return normalized
	if isinstance(value, int):
		normalized = int.__int__(value)
		_validate_safe_integer(normalized, path, "Cannot serialize")
		return normalized
	if isinstance(value, float):
		normalized = float.__float__(value)
		_validate_float(normalized, path, "Cannot serialize")
		return normalized
	return _UNSET


def _decode_scalar(value: Any, path: str) -> Primitive | _Unset:
	if value is None or isinstance(value, bool):
		return value
	if isinstance(value, str):
		normalized = str.__str__(value)
		_validate_portable_string(normalized, path, "Cannot deserialize")
		return normalized
	if isinstance(value, int):
		normalized = int.__int__(value)
		_validate_safe_integer(normalized, path, "Cannot deserialize")
		return normalized
	if isinstance(value, float):
		normalized = float.__float__(value)
		if normalized == 0 and math.copysign(1.0, normalized) < 0:
			return 0.0
		_validate_float(normalized, path, "Cannot deserialize")
		return normalized
	return _UNSET


def _is_referenceable(value: Any) -> bool:
	return (
		isinstance(value, (dt.date, list, tuple, dict, set))
		or _is_dataclass_instance(value)
		or hasattr(value, "__dict__")
	)


def _is_dataclass_instance(value: Any) -> bool:
	return is_dataclass(value) and not isinstance(value, type)


def _datetime_to_wire(value: dt.datetime, path: str) -> str:
	if dt.datetime.utcoffset(value) is None:
		raise ValueError(
			f"Cannot serialize {path}: datetime must be timezone-aware UTC."
		)
	try:
		value = dt.datetime.astimezone(value, dt.UTC)
	except (OverflowError, ValueError) as exc:
		raise ValueError(
			f"Cannot serialize {path}: datetime year must be within 0001-9999."
		) from exc
	value = dt.datetime.fromisoformat(
		dt.datetime.isoformat(value, timespec="microseconds")
	)
	if value.microsecond % 1000 != 0:
		raise ValueError(
			f"Cannot serialize {path}: datetime must use millisecond precision."
		)
	if value.year < 1 or value.year > 9999:
		raise ValueError(
			f"Cannot serialize {path}: datetime year must be within 0001-9999."
		)
	return dt.datetime.isoformat(value, timespec="milliseconds").replace("+00:00", "Z")


def _date_from_wire(value: str, path: str) -> dt.date:
	if not _DATE_RE.fullmatch(value):
		raise ValueError(f"Invalid date literal at {path}: {value!r}")
	try:
		parsed = dt.date.fromisoformat(value)
	except ValueError as exc:
		raise ValueError(f"Invalid date literal at {path}: {value!r}") from exc
	if parsed.isoformat() != value:
		raise ValueError(f"Invalid date literal at {path}: {value!r}")
	return parsed


def _datetime_from_wire(value: str, path: str) -> dt.datetime:
	if not _DATETIME_RE.fullmatch(value):
		raise ValueError(f"Invalid datetime literal at {path}: {value!r}")
	try:
		parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
	except ValueError as exc:
		raise ValueError(f"Invalid datetime literal at {path}: {value!r}") from exc
	if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
		raise ValueError(f"Invalid datetime literal at {path}: {value!r}")
	if parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z") != value:
		raise ValueError(f"Invalid datetime literal at {path}: {value!r}")
	return parsed.astimezone(dt.UTC)


def _sorted_set_items(value: set[Any], path: str) -> list[Any]:
	items: list[Any] = []
	seen_js_keys: set[tuple[Any, ...]] = set()
	seen_python_keys: set[tuple[Any, ...]] = set()
	for index, entry in enumerate(cast(Iterator[Any], set.__iter__(value))):
		entry_path = _path_index(path, index)
		scalar = _encode_scalar(entry, entry_path)
		if scalar is not _UNSET:
			item: Any = scalar
		elif not isinstance(entry, (dt.date, dt.datetime)):
			raise TypeError(
				f"Cannot serialize {entry_path}: set values must be null, booleans, "
				+ "strings, finite numbers, dates, or datetimes."
			)
		else:
			if isinstance(entry, dt.datetime):
				_datetime_to_wire(entry, entry_path)
			item = entry
		js_key = _set_js_key(item)
		python_key = _set_python_key(item)
		if js_key in seen_js_keys or python_key in seen_python_keys:
			raise ValueError(f"Cannot serialize {entry_path}: duplicate set value.")
		seen_js_keys.add(js_key)
		seen_python_keys.add(python_key)
		items.append(item)
	return sorted(items, key=_set_sort_key)


def _set_sort_key(value: Any) -> tuple[Any, ...]:
	if value is None:
		return (0, "")
	if isinstance(value, bool):
		return (1, int(value))
	if isinstance(value, (int, float)):
		return (2, value)
	if isinstance(value, str):
		return (3, value)
	if isinstance(value, dt.datetime):
		return (5, _datetime_to_wire(value, "$"))
	if isinstance(value, dt.date):
		return (4, dt.date.isoformat(value))
	raise TypeError(f"Unsupported set value type: {type(value).__name__}")


def _validate_safe_integer(value: int, path: str, verb: str) -> None:
	if abs(value) > _MAX_SAFE_INTEGER:
		raise ValueError(
			f"{verb} {path}: integer {value} is outside the JavaScript safe integer range."
		)


def _validate_portable_string(value: str, path: str, verb: str) -> None:
	if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
		raise ValueError(f"{verb} {path}: surrogate code points are not portable JSON.")


def _validate_float(value: float, path: str, verb: str) -> None:
	if not math.isfinite(value):
		raise ValueError(f"{verb} {path}: numbers must be finite.")
	if value == 0 and math.copysign(1.0, value) < 0:
		raise ValueError(f"{verb} {path}: negative zero is not portable JSON.")
	if value.is_integer():
		_validate_safe_integer(int(value), path, verb)


def _validate_decoded_set_item(value: Any, path: str) -> None:
	if _decode_scalar(value, path) is not _UNSET:
		return
	if isinstance(value, dt.datetime):
		_datetime_to_wire(value, path)
		return
	if isinstance(value, dt.date):
		return
	raise ValueError(
		f"Cannot deserialize {path}: set values must be null, booleans, strings, "
		+ "finite numbers, dates, or datetimes."
	)


def _set_js_key(value: Any) -> tuple[Any, ...]:
	if value is None:
		return ("null",)
	if isinstance(value, bool):
		return ("bool", value)
	if isinstance(value, (int, float)):
		return ("number", float(value))
	if isinstance(value, str):
		return ("string", value)
	if isinstance(value, dt.datetime):
		return ("datetime-object", id(value))
	if isinstance(value, dt.date):
		return ("date-object", id(value))
	raise TypeError(f"Unsupported set value type: {type(value).__name__}")


def _set_python_key(value: Any) -> tuple[Any, ...]:
	if value is None:
		return ("null",)
	if isinstance(value, bool):
		return ("bool-number", int(value))
	if isinstance(value, (int, float)):
		return ("bool-number", float(value))
	if isinstance(value, str):
		return ("string", value)
	if isinstance(value, dt.datetime):
		return ("datetime", _datetime_to_wire(value, "$"))
	if isinstance(value, dt.date):
		return ("date", dt.date.isoformat(value))
	raise TypeError(f"Unsupported set value type: {type(value).__name__}")


def _decode_identity_id(value: Any, path: str) -> int:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise ValueError(f"Invalid identity id at {path}: {value!r}")
	normalized: int | float
	if isinstance(value, int):
		normalized = int.__int__(value)
	else:
		normalized = float.__float__(value)
	if isinstance(normalized, float) and (
		not math.isfinite(normalized) or not normalized.is_integer()
	):
		raise ValueError(f"Invalid identity id at {path}: {value!r}")
	identity_id = int(normalized)
	_validate_safe_integer(identity_id, path, "Cannot deserialize")
	if identity_id < 0:
		raise ValueError(f"Invalid identity id at {path}: {value!r}")
	return identity_id


def _js_object_key_order(keys: list[str]) -> list[str]:
	indices: list[tuple[int, str]] = []
	others: list[str] = []
	for key in keys:
		if key == "0":
			indices.append((0, key))
		elif (
			key.isascii()
			and key.isdigit()
			and not key.startswith("0")
			and (len(key) < 10 or (len(key) == 10 and key <= "4294967294"))
		):
			indices.append((int(key), key))
		else:
			others.append(key)
	indices.sort(key=lambda item: item[0])
	return [key for _, key in indices] + others


def _path_index(path: str, index: int) -> str:
	return f"{path}[{index}]"


def _path_key(path: str, key: str) -> str:
	if key.isidentifier():
		return f"{path}.{key}"
	return f"{path}[{json.dumps(key)}]"
