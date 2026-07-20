"""Portable Pulse wire serializer."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from pulse._serializer.decoder import Decoder
from pulse._serializer.encoder import Encoder
from pulse._serializer.types import (
	PulseSerializable,
	Serialized,
	SerializerAdapter,
	WireMap,
)

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
		return Encoder(self._adapter_lookup).run(data)

	def deserialize(self, payload: object) -> object:
		"""Deserialize a Pulse wire payload."""
		return Decoder().run(payload)


_DEFAULT_SERIALIZER = Serializer()


def serialize(data: object) -> Serialized:
	"""Serialize with the default serializer."""
	return _DEFAULT_SERIALIZER.serialize(data)


def deserialize(payload: object) -> object:
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
