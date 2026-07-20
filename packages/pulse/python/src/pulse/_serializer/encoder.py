"""Pulse wire encoder."""

# Exact builtin traversal intentionally bypasses overridable subclass APIs.
# Builtin stubs expose those low-level iterators as partially unknown.
# pyright: reportUnknownArgumentType=false, reportUnnecessaryCast=false

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any, cast, final

from pulse._serializer.common import (
	MAX_PROJECTION_STEPS,
	MAX_SAFE_INTEGER,
	PathSegment,
	datetime_to_wire,
	describe_set_value,
	format_path,
	is_js_array_index,
	js_object_key_order,
	validate_finite,
	validate_portable_string,
	validate_safe_integer,
)
from pulse._serializer.types import (
	Primitive,
	PulseSerializable,
	Serialized,
	SerializerAdapter,
	WireMap,
	WireValue,
)


@final
class Encoder:
	__slots__ = ("adapter_lookup", "next_identity", "path", "seen")

	def __init__(
		self, adapter_lookup: Mapping[type[object], SerializerAdapter[Any]]
	) -> None:
		self.adapter_lookup = adapter_lookup
		self.next_identity = 0
		self.path: list[PathSegment] = []
		# Keyed by id(); the tuple pins the object so CPython cannot reuse its
		# id for a fresh adapter projection while this encoder is alive.
		self.seen: dict[int, tuple[object, int]] = {}

	def run(self, data: object) -> Serialized:
		return [5, self.encode(data)]

	def encode(self, value: object) -> WireValue:
		terminal, aliases = self._resolve_custom(value)
		return self._encode_terminal(terminal, aliases)

	def _encode_float(self, value: float) -> WireValue:
		if math.isnan(value):
			return None
		validate_finite(value, self.path, "serialize")
		if value == 0:
			return 0.0
		if abs(value) > MAX_SAFE_INTEGER:
			return ["$", "f", value]
		return value

	def _resolve_custom(self, value: object) -> tuple[object, tuple[object, ...]]:
		aliases: list[object] = []
		chain = {id(value)}
		steps = 0
		current = value
		while True:
			current_type = type(current)
			if current is None or current_type in {
				bool,
				int,
				float,
				str,
				dt.date,
				dt.datetime,
				list,
				tuple,
				dict,
				set,
				WireMap,
			}:
				return current, tuple(aliases)
			if steps >= MAX_PROJECTION_STEPS:
				raise ValueError(
					f"Cannot serialize {format_path(self.path)}: adapter projection "
					+ f"exceeded {MAX_PROJECTION_STEPS} steps."
				)

			adapter = self._find_adapter(current_type)
			if adapter is not None:
				projected = adapter.serialize(current)
			elif isinstance(current, PulseSerializable):
				projected = current.to_pulse()
			elif is_dataclass(current) and not isinstance(current, type):
				return current, tuple(aliases)
			elif isinstance(current, (dict, list, tuple, set)):
				return current, tuple(aliases)
			else:
				raise TypeError(
					f"Cannot serialize {format_path(self.path)}: unsupported value "
					+ f"of type {current_type.__name__}."
				)

			if projected is current:
				raise ValueError(
					f"Cannot serialize {format_path(self.path)}: adapter for "
					+ f"{current_type.__name__} returned its source value."
				)
			projected_id = id(projected)
			if projected_id in chain:
				self._raise_projection_cycle()
			aliases.append(current)
			chain.add(projected_id)
			current = projected
			steps += 1

	def _raise_projection_cycle(self) -> None:
		raise ValueError(
			f"Cannot serialize {format_path(self.path)}: adapter projection cycle."
		)

	def _find_adapter(self, value_type: type[object]) -> SerializerAdapter[Any] | None:
		adapter = self.adapter_lookup.get(value_type)
		if adapter is not None:
			return adapter
		for base in value_type.__mro__[1:]:
			adapter = self.adapter_lookup.get(base)
			if adapter is not None:
				return adapter
		return None

	def _encode_terminal(self, value: object, aliases: tuple[object, ...]) -> WireValue:
		value_type = type(value)
		if value is None or value_type is bool:
			return cast(Primitive, value)
		if value_type is str:
			if not cast(str, value).isascii():
				validate_portable_string(cast(str, value), self.path, "serialize")
			return cast(str, value)
		if value_type is int:
			validate_safe_integer(cast(int, value), self.path, "serialize")
			return cast(int, value)
		if value_type is float:
			return self._encode_float(cast(float, value))

		if not aliases:
			existing = self.seen.get(id(value))
			if existing is not None:
				return ["$", existing[1]]
			identity = self.next_identity
			self.next_identity += 1
			self.seen[id(value)] = (value, identity)
		else:
			identity, seen = self._claim_aliased_identity(value, aliases)
			if seen:
				return ["$", identity]

		if value_type is dt.datetime:
			return ["$", "t", datetime_to_wire(cast(dt.datetime, value), self.path)]
		if value_type is dt.date:
			midnight = dt.datetime.combine(cast(dt.date, value), dt.time(), dt.UTC)
			return ["$", "t", datetime_to_wire(midnight, self.path)]
		if isinstance(value, WireMap):
			return self._encode_map(cast(dict[object, object], value))
		if isinstance(value, dict):
			return self._encode_record(cast(dict[object, object], value))
		if isinstance(value, (list, tuple)):
			return self._encode_array(value)
		if isinstance(value, set):
			return self._encode_set(value)
		if is_dataclass(value) and not isinstance(value, type):
			return self._encode_dataclass(value)
		raise TypeError(
			f"Cannot serialize {format_path(self.path)}: unsupported value "
			+ f"of type {value_type.__name__}."
		)

	def _claim_aliased_identity(
		self, value: object, aliases: tuple[object, ...]
	) -> tuple[int, bool]:
		values = (*aliases, value)
		existing = {self.seen[id(item)][1] for item in values if id(item) in self.seen}
		if len(existing) > 1:
			raise ValueError(
				f"Cannot serialize {format_path(self.path)}: adapter projection "
				+ "combines values with different identities."
			)
		if existing:
			identity = existing.pop()
			for item in values:
				self.seen[id(item)] = (item, identity)
			return identity, True
		identity = self.next_identity
		self.next_identity += 1
		for item in values:
			self.seen[id(item)] = (item, identity)
		return identity, False

	def _encode_array(self, value: object) -> list[WireValue]:
		if isinstance(value, list):
			iterator = list.__iter__(value)
		else:
			iterator = tuple.__iter__(cast(tuple[object, ...], value))
		items: list[WireValue] = []
		for index, entry in enumerate(iterator):
			self.path.append(index)
			items.append(self.encode(entry))
			self.path.pop()
		if items and type(items[0]) is str and items[0] == "$":
			return ["$", "a", items]
		return items

	def _encode_record(self, value: dict[object, object]) -> dict[str, WireValue]:
		requires_ordering = False
		for raw_key in dict.__iter__(value):
			if type(raw_key) is not str:
				raise TypeError(
					f"Cannot serialize {format_path(self.path)}: record keys must be strings, "
					+ f"got {type(raw_key).__name__}."
				)
			key = cast(str, raw_key)
			if not key.isascii():
				validate_portable_string(key, self.path, "serialize")
			if is_js_array_index(key):
				requires_ordering = True
		keys = (
			js_object_key_order(cast(list[str], list(dict.__iter__(value))))
			if requires_ordering
			else cast(Iterable[str], dict.__iter__(value))
		)
		result: dict[str, WireValue] = {}
		for key in keys:
			self.path.append(key)
			result[key] = self.encode(dict.__getitem__(value, key))
			self.path.pop()
		return result

	def _encode_map(self, value: dict[object, object]) -> list[WireValue]:
		items: list[WireValue] = []
		for raw_key, entry in dict.items(value):
			if type(raw_key) is not str:
				raise TypeError(
					f"Cannot serialize {format_path(self.path)}: map keys must be strings, "
					+ f"got {type(raw_key).__name__}."
				)
			key = cast(str, raw_key)
			validate_portable_string(key, self.path, "serialize")
			self.path.append(key)
			encoded = self.encode(entry)
			self.path.pop()
			items.append([key, encoded])
		return ["$", "m", items]

	def _encode_dataclass(self, value: object) -> dict[str, WireValue]:
		result: dict[str, WireValue] = {}
		for dataclass_field in fields(cast(Any, value)):
			key = dataclass_field.name
			self.path.append(key)
			result[key] = self.encode(object.__getattribute__(value, key))
			self.path.pop()
		return result

	# Wire order is sorted, not iteration order: Python set iteration varies
	# per process (string hash randomization), and the wire must be
	# deterministic for identical values.
	def _encode_set(self, value: set[object]) -> list[WireValue]:
		portable: list[tuple[tuple[Any, ...], object, tuple[object, ...]]] = []
		seen_js: set[tuple[Any, ...]] = set()
		seen_python: set[tuple[Any, ...]] = set()
		for index, source in enumerate(set.__iter__(value)):
			self.path.append(("set", index))
			terminal, aliases = self._resolve_custom(source)
			terminal, sort_key, js_key, python_key = describe_set_value(
				terminal, self.path, "serialize"
			)
			if js_key in seen_js or python_key in seen_python:
				raise ValueError(
					f"Cannot serialize {format_path(self.path)}: duplicate set value."
				)
			seen_js.add(js_key)
			seen_python.add(python_key)
			portable.append((sort_key, terminal, aliases))
			self.path.pop()
		portable.sort(key=lambda item: item[0])

		items: list[WireValue] = []
		for index, (_, terminal, aliases) in enumerate(portable):
			self.path.append(("set", index))
			items.append(self._encode_terminal(terminal, aliases))
			self.path.pop()
		return ["$", "s", items]
