"""Portable Pulse wire serializer."""

# Exact builtin traversal intentionally bypasses overridable subclass APIs.
# Builtin stubs expose those low-level iterators as partially unknown.
# pyright: reportUnknownArgumentType=false, reportUnnecessaryCast=false

from __future__ import annotations

import datetime as dt
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Generic, TypeAlias, TypeVar, cast, final

Primitive: TypeAlias = None | bool | int | float | str
WireValue: TypeAlias = Primitive | list["WireValue"] | dict[str, "WireValue"]
Serialized: TypeAlias = list[Any]

_MAX_SAFE_INTEGER = 2**53 - 1
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


class WireMap(dict[str, Any]):
	"""Dict subclass that round-trips as a JavaScript Map."""


class PulseSerializable(ABC):
	"""A value that projects itself into Pulse's portable domain."""

	@abstractmethod
	def to_pulse(self) -> object:
		"""Return the portable projection for this value."""


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SerializerAdapter(Generic[T]):
	"""Portable projection for a Python type."""

	type: type[T]
	serialize: Callable[[T], object]


_CORE_ADAPTER_TARGETS = frozenset(
	{
		object,
		type(None),
		bool,
		int,
		float,
		str,
		list,
		tuple,
		dict,
		set,
		dt.date,
		dt.datetime,
		WireMap,
	}
)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Serializer:
	"""Immutable serializer with an ordered set of type adapters."""

	_adapter_lookup: Mapping[type[object], SerializerAdapter[Any]] = field(repr=False)

	def __init__(self, adapters: Iterable[SerializerAdapter[Any]] = ()) -> None:
		lookup: dict[type[object], SerializerAdapter[Any]] = {}
		for adapter in adapters:
			target = adapter.type
			if not isinstance(target, type):
				raise TypeError("Serializer adapter target must be a type.")
			if target in _CORE_ADAPTER_TARGETS:
				raise ValueError(
					f"Cannot register a serializer adapter for core type {target.__name__}."
				)
			if target in lookup:
				raise ValueError(
					f"Duplicate serializer adapter target: {target.__name__}."
				)
			if not callable(adapter.serialize):
				raise TypeError(
					f"Serializer adapter for {target.__name__} must be callable."
				)
			lookup[target] = adapter
		object.__setattr__(self, "_adapter_lookup", MappingProxyType(lookup))

	def serialize(self, data: object) -> Serialized:
		"""Serialize a Python value to Pulse's wire format."""
		return _Encoder(self._adapter_lookup).run(data)

	def deserialize(self, payload: Serialized) -> Any:
		"""Deserialize a Pulse wire payload."""
		return _Decoder().run(payload)


_DEFAULT_SERIALIZER = Serializer()


def serialize(data: object) -> Serialized:
	"""Serialize with the default serializer."""
	return _DEFAULT_SERIALIZER.serialize(data)


def deserialize(payload: Serialized) -> Any:
	"""Deserialize with the default serializer."""
	return _DEFAULT_SERIALIZER.deserialize(payload)


__all__ = [
	"PulseSerializable",
	"Serialized",
	"Serializer",
	"SerializerAdapter",
	"WireMap",
	"deserialize",
	"serialize",
]


type _PathSegment = str | int | tuple[str, int]


@final
class _Encoder:
	__slots__ = ("adapter_lookup", "next_identity", "path", "seen")

	def __init__(
		self, adapter_lookup: Mapping[type[object], SerializerAdapter[Any]]
	) -> None:
		self.adapter_lookup = adapter_lookup
		self.next_identity = 0
		self.path: list[_PathSegment] = []
		self.seen: dict[int, int] = {}

	def run(self, data: object) -> Serialized:
		return [5, self.encode(data)]

	def encode(self, value: object) -> WireValue:
		value_type = type(value)
		if value is None or value_type is bool:
			return cast(Primitive, value)
		if value_type is str:
			if not cast(str, value).isascii():
				_validate_portable_string(cast(str, value), self.path, "serialize")
			return cast(str, value)
		if value_type is int:
			_validate_safe_integer(cast(int, value), self.path, "serialize")
			return cast(int, value)
		if value_type is float:
			return self._encode_float(cast(float, value))
		if (
			value_type is list
			or value_type is dict
			or value_type is tuple
			or value_type is set
			or value_type is dt.date
			or value_type is dt.datetime
			or value_type is WireMap
		):
			return self._encode_terminal(value, ())

		terminal, aliases = self._resolve_custom(value)
		return self._encode_terminal(terminal, aliases)

	def _encode_float(self, value: float) -> Primitive:
		if math.isnan(value):
			return None
		_validate_float(value, self.path, "serialize", reject_negative_zero=True)
		return value

	def _resolve_custom(self, value: object) -> tuple[object, tuple[object, ...]]:
		aliases: list[object] = []
		chain = {id(value)}
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
					f"Cannot serialize {_format_path(self.path)}: unsupported value "
					+ f"of type {current_type.__name__}."
				)

			if projected is current:
				raise ValueError(
					f"Cannot serialize {_format_path(self.path)}: adapter for "
					+ f"{current_type.__name__} returned its source value."
				)
			projected_id = id(projected)
			if projected_id in chain:
				raise ValueError(
					f"Cannot serialize {_format_path(self.path)}: adapter projection cycle."
				)
			aliases.append(current)
			chain.add(projected_id)
			current = projected

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
				_validate_portable_string(cast(str, value), self.path, "serialize")
			return cast(str, value)
		if value_type is int:
			_validate_safe_integer(cast(int, value), self.path, "serialize")
			return cast(int, value)
		if value_type is float:
			return self._encode_float(cast(float, value))

		if not aliases:
			value_id = id(value)
			existing_identity = self.seen.get(value_id)
			if existing_identity is not None:
				return ["$", existing_identity]
			identity = self.next_identity
			self.next_identity += 1
			self.seen[value_id] = identity
		else:
			identity, seen = self._claim_aliased_identity(value, aliases)
			if seen:
				return ["$", identity]

		if value_type is dt.datetime:
			return ["$", "t", _datetime_to_wire(cast(dt.datetime, value), self.path)]
		if value_type is dt.date:
			midnight = dt.datetime.combine(cast(dt.date, value), dt.time(), dt.UTC)
			return ["$", "t", _datetime_to_wire(midnight, self.path)]
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
			f"Cannot serialize {_format_path(self.path)}: unsupported value "
			+ f"of type {value_type.__name__}."
		)

	def _claim_aliased_identity(
		self, value: object, aliases: tuple[object, ...]
	) -> tuple[int, bool]:
		values = (*aliases, value)
		existing = {self.seen[id(value)] for value in values if id(value) in self.seen}
		if len(existing) > 1:
			raise ValueError(
				f"Cannot serialize {_format_path(self.path)}: adapter projection "
				+ "combines values with different identities."
			)
		if existing:
			identity = existing.pop()
			for value in values:
				self.seen[id(value)] = identity
			return identity, True
		identity = self.next_identity
		self.next_identity += 1
		for value in values:
			self.seen[id(value)] = identity
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
					f"Cannot serialize {_format_path(self.path)}: record keys must be strings, "
					+ f"got {type(raw_key).__name__}."
				)
			key = cast(str, raw_key)
			if not key.isascii():
				_validate_portable_string(key, self.path, "serialize")
			if key == "0" or (
				key
				and "1" <= key[0] <= "9"
				and key.isdigit()
				and not key.startswith("0")
				and (len(key) < 10 or (len(key) == 10 and key <= "4294967294"))
			):
				requires_ordering = True
		keys = (
			_js_object_key_order(cast(list[str], list(dict.__iter__(value))))
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
					f"Cannot serialize {_format_path(self.path)}: map keys must be strings, "
					+ f"got {type(raw_key).__name__}."
				)
			key = cast(str, raw_key)
			_validate_portable_string(key, self.path, "serialize")
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

	def _encode_set(self, value: set[object]) -> list[WireValue]:
		portable: list[tuple[tuple[Any, ...], object, tuple[object, ...]]] = []
		seen_js: set[tuple[Any, ...]] = set()
		seen_python: set[tuple[Any, ...]] = set()
		for index, source in enumerate(set.__iter__(value)):
			self.path.append(("set", index))
			source_type = type(source)
			aliases: tuple[object, ...] = ()
			if source is None:
				terminal = None
				sort_key = (0, "")
				js_key = python_key = ("null",)
			elif source_type is bool:
				terminal = source
				sort_key = (1, int(cast(bool, source)))
				js_key = ("bool", source)
				python_key = ("bool-number", int(cast(bool, source)))
			elif source_type is int:
				terminal = source
				_validate_safe_integer(cast(int, source), self.path, "serialize")
				sort_key = (2, source)
				js_key = ("number", float(cast(int, source)))
				python_key = ("bool-number", float(cast(int, source)))
			elif source_type is float:
				if math.isnan(cast(float, source)):
					terminal = None
					sort_key = (0, "")
					js_key = python_key = ("null",)
				else:
					terminal = source
					_validate_float(
						cast(float, source),
						self.path,
						"serialize",
						reject_negative_zero=True,
					)
					sort_key = (2, source)
					js_key = ("number", cast(float, source))
					python_key = ("bool-number", cast(float, source))
			elif source_type is str:
				terminal = source
				if not cast(str, source).isascii():
					_validate_portable_string(cast(str, source), self.path, "serialize")
				sort_key = (3, source)
				js_key = python_key = ("string", source)
			elif source_type is dt.date or source_type is dt.datetime:
				terminal = source
				wire = _temporal_to_wire(source, self.path)
				sort_key = (4, wire)
				js_key = ("datetime-object", id(source))
				python_key = ("datetime", wire)
			else:
				terminal, aliases, sort_key, js_key, python_key = (
					self._resolve_set_item(source)
				)
			if js_key in seen_js or python_key in seen_python:
				raise ValueError(
					f"Cannot serialize {_format_path(self.path)}: duplicate set value."
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

	def _resolve_set_item(
		self, value: object
	) -> tuple[
		object,
		tuple[object, ...],
		tuple[Any, ...],
		tuple[Any, ...],
		tuple[Any, ...],
	]:
		terminal, aliases = self._resolve_custom(value)
		terminal_type = type(terminal)
		if terminal_type is float and math.isnan(cast(float, terminal)):
			return None, (), (0, ""), ("null",), ("null",)
		if terminal is None:
			return terminal, aliases, (0, ""), ("null",), ("null",)
		if terminal_type is bool:
			return (
				terminal,
				aliases,
				(1, int(cast(bool, terminal))),
				("bool", terminal),
				("bool-number", int(cast(bool, terminal))),
			)
		if terminal_type is int:
			_validate_safe_integer(cast(int, terminal), self.path, "serialize")
			return (
				terminal,
				aliases,
				(2, terminal),
				("number", float(cast(int, terminal))),
				("bool-number", float(cast(int, terminal))),
			)
		if terminal_type is float:
			_validate_float(
				cast(float, terminal),
				self.path,
				"serialize",
				reject_negative_zero=True,
			)
			return (
				terminal,
				aliases,
				(2, terminal),
				("number", terminal),
				("bool-number", terminal),
			)
		if terminal_type is str:
			_validate_portable_string(cast(str, terminal), self.path, "serialize")
			return (
				terminal,
				aliases,
				(3, terminal),
				("string", terminal),
				("string", terminal),
			)
		if terminal_type is dt.date or terminal_type is dt.datetime:
			wire = _temporal_to_wire(terminal, self.path)
			return (
				terminal,
				aliases,
				(4, wire),
				("datetime-object", id(terminal)),
				("datetime", wire),
			)
		raise TypeError(
			f"Cannot serialize {_format_path(self.path)}: set values must project to "
			+ "null, booleans, strings, finite numbers, dates, or datetimes."
		)


@final
class _Decoder:
	__slots__ = ("identities", "path")

	def __init__(self) -> None:
		self.identities: list[Any] = []
		self.path: list[_PathSegment] = []

	def run(self, payload: Serialized) -> Any:
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
				_validate_portable_string(value, self.path, "deserialize")
			return value
		if value_type is int:
			_validate_safe_integer(value, self.path, "deserialize")
			return value
		if value_type is float:
			_validate_float(value, self.path, "deserialize", reject_negative_zero=False)
			return 0.0 if value == 0 else value
		if value_type is list:
			if value and type(value[0]) is str and value[0] == "$":
				if len(value) == 2 and type(value[1]) is int:
					identity = cast(int, value[1])
					if 0 <= identity < len(self.identities):
						return self.identities[identity]
					if abs(identity) > _MAX_SAFE_INTEGER:
						_validate_safe_integer(identity, self.path, "deserialize")
					if identity < 0:
						raise ValueError(
							f"Invalid identity id at {_format_path(self.path)}: {identity!r}"
						)
					raise ValueError(
						f"Dangling reference at {_format_path(self.path)}: {identity}"
					)
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
			f"Cannot deserialize {_format_path(self.path)}: unsupported wire value "
			+ f"of type {value_type.__name__}."
		)

	def _decode_marker(self, marker: list[Any]) -> Any:
		if len(marker) == 2 and type(marker[1]) in {int, float}:
			identity = _decode_identity_id(marker[1], self.path)
			if identity >= len(self.identities):
				raise ValueError(
					f"Dangling reference at {_format_path(self.path)}: {identity}"
				)
			return self.identities[identity]
		if len(marker) < 2 or type(marker[1]) is not str:
			raise ValueError(
				f'Malformed marker at {_format_path(self.path)}: expected ["$", tag, ...].'
			)

		tag = cast(str, marker[1])
		if tag == "a":
			if len(marker) != 3 or type(marker[2]) is not list:
				raise ValueError(
					f"Malformed array marker at {_format_path(self.path)}."
				)
			items = cast(list[Any], marker[2])
			if not items or type(items[0]) is not str or items[0] != "$":
				raise ValueError(
					f"Malformed array marker at {_format_path(self.path)}: payload must begin with '$'."
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
					f"Malformed datetime marker at {_format_path(self.path)}."
				)
			datetime_result = _datetime_from_wire(cast(str, marker[2]), self.path)
			self.identities.append(datetime_result)
			return datetime_result
		if tag == "m":
			return self._decode_map(marker)
		if tag == "s":
			return self._decode_set(marker)
		raise ValueError(
			f"Unknown wire marker tag at {_format_path(self.path)}: {tag!r}"
		)

	def _decode_record(self, entries: dict[Any, Any]) -> dict[str, Any]:
		result: dict[str, Any] = {}
		self.identities.append(result)
		requires_ordering = False
		for key in dict.__iter__(entries):
			if type(key) is not str:
				raise ValueError(
					f"Malformed record at {_format_path(self.path)}: keys must be strings, "
					+ f"got {type(key).__name__}."
				)
			if not key.isascii():
				_validate_portable_string(key, self.path, "deserialize")
			if key == "0" or (
				key
				and "1" <= key[0] <= "9"
				and key.isdigit()
				and not key.startswith("0")
				and (len(key) < 10 or (len(key) == 10 and key <= "4294967294"))
			):
				requires_ordering = True
		keys = (
			_js_object_key_order(cast(list[str], list(dict.__iter__(entries))))
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
			raise ValueError(f"Malformed map marker at {_format_path(self.path)}.")
		result = WireMap()
		self.identities.append(result)
		seen_keys: set[str] = set()
		for index, raw_entry in enumerate(cast(list[Any], marker[2])):
			if type(raw_entry) is not list or len(raw_entry) != 2:
				raise ValueError(
					f"Malformed map entry at {_format_child_path(self.path, index)}: "
					+ "expected [string_key, value]."
				)
			key = raw_entry[0]
			if type(key) is not str:
				raise ValueError(
					f"Malformed map entry at {_format_child_path(self.path, index)}: "
					+ "expected [string_key, value]."
				)
			_validate_portable_string(key, self.path, "deserialize")
			if key in seen_keys:
				raise ValueError(
					f"Duplicate map key at {_format_child_path(self.path, index)}: {key!r}"
				)
			seen_keys.add(key)
			self.path.append(key)
			result[key] = self.decode(raw_entry[1])
			self.path.pop()
		return result

	def _decode_set(self, marker: list[Any]) -> set[Any]:
		if len(marker) != 3 or type(marker[2]) is not list:
			raise ValueError(f"Malformed set marker at {_format_path(self.path)}.")
		result: set[Any] = set()
		self.identities.append(result)
		seen_js: set[tuple[Any, ...]] = set()
		seen_python: set[tuple[Any, ...]] = set()
		previous: tuple[Any, ...] | None = None
		for index, entry in enumerate(cast(list[Any], marker[2])):
			self.path.append(("set", index))
			item = self.decode(entry)
			item_type = type(item)
			if item is None:
				sort_key = (0, "")
				js_key = python_key = ("null",)
			elif item_type is bool:
				sort_key = (1, int(cast(bool, item)))
				js_key = ("bool", item)
				python_key = ("bool-number", int(cast(bool, item)))
			elif item_type is int:
				sort_key = (2, item)
				js_key = ("number", float(cast(int, item)))
				python_key = ("bool-number", float(cast(int, item)))
			elif item_type is float:
				sort_key = (2, item)
				js_key = ("number", cast(float, item))
				python_key = ("bool-number", cast(float, item))
			elif item_type is str:
				sort_key = (3, item)
				js_key = python_key = ("string", item)
			elif item_type is dt.datetime:
				wire = _datetime_to_wire(cast(dt.datetime, item), self.path)
				sort_key = (4, wire)
				js_key = ("datetime-object", id(item))
				python_key = ("datetime", wire)
			else:
				raise ValueError(
					f"Cannot deserialize {_format_path(self.path)}: set values must be "
					+ "null, booleans, strings, finite numbers, or datetimes."
				)
			if previous is not None and sort_key < previous:
				raise ValueError(
					f"Set entries are not canonically ordered at {_format_path(self.path)}."
				)
			previous = sort_key
			if js_key in seen_js:
				raise ValueError(f"Duplicate set entry at {_format_path(self.path)}.")
			if python_key in seen_python:
				raise ValueError(
					f"Set entry at {_format_path(self.path)} collides under Python equality."
				)
			seen_js.add(js_key)
			seen_python.add(python_key)
			result.add(item)
			self.path.pop()
		return result


def _validate_safe_integer(value: int, path: list[_PathSegment], verb: str) -> None:
	if abs(value) > _MAX_SAFE_INTEGER:
		raise ValueError(
			f"Cannot {verb} {_format_path(path)}: integer {value} is outside the "
			+ "JavaScript safe integer range."
		)


def _validate_float(
	value: float,
	path: list[_PathSegment],
	verb: str,
	*,
	reject_negative_zero: bool,
) -> None:
	if not math.isfinite(value):
		raise ValueError(f"Cannot {verb} {_format_path(path)}: numbers must be finite.")
	if reject_negative_zero and value == 0 and math.copysign(1.0, value) < 0:
		raise ValueError(
			f"Cannot {verb} {_format_path(path)}: negative zero is not portable JSON."
		)
	if value.is_integer():
		_validate_safe_integer(int(value), path, verb)


def _validate_portable_string(value: str, path: list[_PathSegment], verb: str) -> None:
	if value.isascii():
		return
	if _SURROGATE_RE.search(value) is not None:
		raise ValueError(
			f"Cannot {verb} {_format_path(path)}: surrogate code points are not portable JSON."
		)


def _temporal_to_wire(value: object, path: list[_PathSegment]) -> str:
	if type(value) is dt.date:
		value = dt.datetime.combine(cast(dt.date, value), dt.time(), dt.UTC)
	return _datetime_to_wire(cast(dt.datetime, value), path)


def _datetime_to_wire(value: dt.datetime, path: list[_PathSegment]) -> str:
	if dt.datetime.utcoffset(value) is None:
		raise ValueError(
			f"Cannot serialize {_format_path(path)}: datetime must be timezone-aware."
		)
	try:
		normalized = dt.datetime.astimezone(value, dt.UTC)
	except (OverflowError, ValueError) as exc:
		raise ValueError(
			f"Cannot serialize {_format_path(path)}: datetime year must be within 0001-9999."
		) from exc
	if normalized.microsecond % 1000 != 0:
		raise ValueError(
			f"Cannot serialize {_format_path(path)}: datetime must use millisecond precision."
		)
	return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime_from_wire(value: str, path: list[_PathSegment]) -> dt.datetime:
	if not _DATETIME_RE.fullmatch(value):
		raise ValueError(f"Invalid datetime literal at {_format_path(path)}: {value!r}")
	try:
		parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
	except ValueError as exc:
		raise ValueError(
			f"Invalid datetime literal at {_format_path(path)}: {value!r}"
		) from exc
	return parsed


def _decode_identity_id(value: object, path: list[_PathSegment]) -> int:
	if type(value) not in {int, float}:
		raise ValueError(f"Invalid identity id at {_format_path(path)}: {value!r}")
	if type(value) is float and (
		not math.isfinite(cast(float, value)) or not cast(float, value).is_integer()
	):
		raise ValueError(f"Invalid identity id at {_format_path(path)}: {value!r}")
	identity = int(cast(int | float, value))
	_validate_safe_integer(identity, path, "deserialize")
	if identity < 0:
		raise ValueError(f"Invalid identity id at {_format_path(path)}: {value!r}")
	return identity


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


def _format_child_path(path: list[_PathSegment], segment: _PathSegment) -> str:
	path.append(segment)
	formatted = _format_path(path)
	path.pop()
	return formatted


def _format_path(path: list[_PathSegment]) -> str:
	result = "$"
	for segment in path:
		if isinstance(segment, int):
			result += f"[{segment}]"
		elif isinstance(segment, tuple):
			result += f"<set:{segment[1]}>"
		elif segment.isidentifier():
			result += f".{segment}"
		else:
			result += f"[{json.dumps(segment)}]"
	return result
