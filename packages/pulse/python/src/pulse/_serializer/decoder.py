"""Pulse wire decoder."""

# Exact builtin traversal intentionally bypasses overridable subclass APIs.
# Builtin stubs expose those low-level iterators as partially unknown.
# pyright: reportUnknownArgumentType=false, reportUnnecessaryCast=false

import math
from collections.abc import Iterable
from typing import Any, cast, final

from pulse._serializer.common import (
	MAX_SAFE_INTEGER,
	PathSegment,
	datetime_from_wire,
	decode_identity_id,
	describe_set_value,
	format_child_path,
	format_path,
	is_js_array_index,
	js_object_key_order,
	validate_finite,
	validate_portable_string,
	validate_safe_integer,
)
from pulse._serializer.types import WireMap


@final
class Decoder:
	__slots__ = ("identities", "path")

	def __init__(self) -> None:
		self.identities: list[Any] = []
		self.path: list[PathSegment] = []

	def run(self, payload: object) -> object:
		if type(payload) is not list or len(payload) != 2:
			raise TypeError("Wire payload must be a two-item list: [5, wire_value].")
		version = payload[0]
		if type(version) not in {int, float} or version != 5:
			raise ValueError(f"Unknown wire version: {version!r}")
		return self.decode(payload[1])

	def decode(self, value: Any) -> Any:
		value_type = type(value)
		if value is None or value_type is bool:
			return value
		if value_type is str:
			if not value.isascii():
				validate_portable_string(value, self.path, "deserialize")
			return value
		if value_type is int:
			validate_safe_integer(value, self.path, "deserialize")
			return value
		if value_type is float:
			validate_finite(value, self.path, "deserialize")
			if abs(value) > MAX_SAFE_INTEGER:
				raise ValueError(
					f"Cannot deserialize {format_path(self.path)}: numbers beyond "
					+ "the safe integer range must use the big-float marker."
				)
			return 0.0 if value == 0 else value
		if value_type is list:
			if value and type(value[0]) is str and value[0] == "$":
				return self._decode_marker(value)
			result: list[Any] = []
			self.identities.append(result)
			for index, entry in enumerate(value):
				self.path.append(index)
				result.append(self.decode(entry))
				self.path.pop()
			return result
		if value_type is dict:
			return self._decode_record(value)
		raise TypeError(
			f"Cannot deserialize {format_path(self.path)}: unsupported wire value "
			+ f"of type {value_type.__name__}."
		)

	def _decode_marker(self, marker: list[Any]) -> Any:
		if len(marker) == 2 and type(marker[1]) in {int, float}:
			identity = decode_identity_id(marker[1], self.path)
			if identity >= len(self.identities):
				raise ValueError(
					f"Dangling reference at {format_path(self.path)}: {identity}"
				)
			return self.identities[identity]
		if len(marker) < 2 or type(marker[1]) is not str:
			raise ValueError(
				f'Malformed marker at {format_path(self.path)}: expected ["$", tag, ...].'
			)

		tag = cast(str, marker[1])
		if tag == "a":
			if len(marker) != 3 or type(marker[2]) is not list:
				raise ValueError(f"Malformed array marker at {format_path(self.path)}.")
			items = cast(list[Any], marker[2])
			if not items or type(items[0]) is not str or items[0] != "$":
				raise ValueError(
					f"Malformed array marker at {format_path(self.path)}: payload must begin with '$'."
				)
			result: list[Any] = []
			self.identities.append(result)
			for index, entry in enumerate(items):
				self.path.append(index)
				result.append(self.decode(entry))
				self.path.pop()
			return result
		if tag == "t":
			if len(marker) != 3 or type(marker[2]) is not str:
				raise ValueError(
					f"Malformed datetime marker at {format_path(self.path)}."
				)
			datetime_result = datetime_from_wire(cast(str, marker[2]), self.path)
			self.identities.append(datetime_result)
			return datetime_result
		if tag == "f":
			if len(marker) != 3 or type(marker[2]) not in {int, float}:
				raise ValueError(
					f"Malformed big-float marker at {format_path(self.path)}."
				)
			# int payloads come from JSON.stringify emitting large integral
			# doubles as integer literals; both runtimes round them to the
			# nearest double identically.
			number = float(cast(int | float, marker[2]))
			if not math.isfinite(number) or abs(number) <= MAX_SAFE_INTEGER:
				raise ValueError(
					f"Malformed big-float marker at {format_path(self.path)}."
				)
			return number
		if tag == "m":
			return self._decode_map(marker)
		if tag == "s":
			return self._decode_set(marker)
		raise ValueError(
			f"Unknown wire marker tag at {format_path(self.path)}: {tag!r}"
		)

	def _decode_record(self, entries: dict[Any, Any]) -> dict[str, Any]:
		result: dict[str, Any] = {}
		self.identities.append(result)
		requires_ordering = False
		for key in dict.__iter__(entries):
			if type(key) is not str:
				raise ValueError(
					f"Malformed record at {format_path(self.path)}: keys must be strings, "
					+ f"got {type(key).__name__}."
				)
			if not key.isascii():
				validate_portable_string(key, self.path, "deserialize")
			if is_js_array_index(key):
				requires_ordering = True
		keys = (
			js_object_key_order(cast(list[str], list(dict.__iter__(entries))))
			if requires_ordering
			else cast(Iterable[str], dict.__iter__(entries))
		)
		for key in keys:
			self.path.append(key)
			result[key] = self.decode(dict.__getitem__(entries, key))
			self.path.pop()
		return result

	def _decode_map(self, marker: list[Any]) -> WireMap:
		if len(marker) != 3 or type(marker[2]) is not list:
			raise ValueError(f"Malformed map marker at {format_path(self.path)}.")
		result = WireMap()
		self.identities.append(result)
		seen_keys: set[str] = set()
		for index, raw_entry in enumerate(cast(list[Any], marker[2])):
			if type(raw_entry) is not list or len(raw_entry) != 2:
				raise ValueError(
					f"Malformed map entry at {format_child_path(self.path, index)}: "
					+ "expected [string_key, value]."
				)
			key = raw_entry[0]
			if type(key) is not str:
				raise ValueError(
					f"Malformed map entry at {format_child_path(self.path, index)}: "
					+ "expected [string_key, value]."
				)
			validate_portable_string(key, self.path, "deserialize")
			if key in seen_keys:
				raise ValueError(
					f"Duplicate map key at {format_child_path(self.path, index)}: {key!r}"
				)
			seen_keys.add(key)
			self.path.append(key)
			result[key] = self.decode(raw_entry[1])
			self.path.pop()
		return result

	def _decode_set(self, marker: list[Any]) -> set[Any]:
		if len(marker) != 3 or type(marker[2]) is not list:
			raise ValueError(f"Malformed set marker at {format_path(self.path)}.")
		result: set[Any] = set()
		self.identities.append(result)
		seen_js: set[tuple[Any, ...]] = set()
		seen_python: set[tuple[Any, ...]] = set()
		previous: tuple[Any, ...] | None = None
		for index, entry in enumerate(cast(list[Any], marker[2])):
			self.path.append(("set", index))
			item = self.decode(entry)
			item, sort_key, js_key, python_key = describe_set_value(
				item, self.path, "deserialize"
			)
			if previous is not None and sort_key < previous:
				raise ValueError(
					f"Set entries are not canonically ordered at {format_path(self.path)}."
				)
			previous = sort_key
			if js_key in seen_js:
				raise ValueError(f"Duplicate set entry at {format_path(self.path)}.")
			if python_key in seen_python:
				raise ValueError(
					f"Set entry at {format_path(self.path)} collides under Python equality."
				)
			seen_js.add(js_key)
			seen_python.add(python_key)
			result.add(item)
			self.path.pop()
		return result
