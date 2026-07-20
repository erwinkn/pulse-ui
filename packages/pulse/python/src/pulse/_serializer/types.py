from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeAlias, TypeVar

Primitive: TypeAlias = None | bool | int | float | str
WireValue: TypeAlias = Primitive | list["WireValue"] | dict[str, "WireValue"]
Serialized: TypeAlias = list[WireValue]


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
