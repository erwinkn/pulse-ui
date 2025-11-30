"""Unified JS import system for javascript_v2."""

from collections.abc import Callable, Sequence
from typing import Literal, TypeVar, TypeVarTuple, overload, override

from pulse.javascript_v2.ids import generate_id

T = TypeVar("T")
Args = TypeVarTuple("Args")
R = TypeVar("R")

# Global registry for all Import objects
IMPORT_REGISTRY: set["Import"] = set()


class Import:
	"""Universal import descriptor. Registers itself on creation."""

	name: str
	src: str
	kind: Literal["default", "named", "type", "side_effect"]
	before: tuple[str, ...]
	# For runtime expression computation
	prop: str | None
	id: str

	def __init__(
		self,
		name: str,
		src: str,
		kind: Literal["default", "named", "type", "side_effect"] = "named",
		before: Sequence[str] = (),
		*,
		prop: str | None = None,
		register: bool = True,
	) -> None:
		self.name = name
		self.src = src
		self.kind = kind
		self.before = tuple(before)
		self.prop = prop
		self.id = generate_id()
		if register:
			IMPORT_REGISTRY.add(self)

	@classmethod
	def default(
		cls,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "default", prop=prop, register=register)

	@classmethod
	def named(
		cls,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "named", prop=prop, register=register)

	@classmethod
	def type_(
		cls,
		name: str,
		src: str,
		*,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "type", register=register)

	@classmethod
	def css(
		cls,
		src: str,
		before: Sequence[str] = (),
		*,
		register: bool = True,
	) -> "Import":
		return cls("", src, "side_effect", before, register=register)

	@property
	def is_default(self) -> bool:
		return self.kind == "default"

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this import."""
		return f"{self.name}_{self.id}"

	@property
	def expr(self) -> str:
		"""Runtime expression for this import."""
		base = self.js_name
		if self.prop:
			return f"{base}.{self.prop}"
		return base

	@override
	def __eq__(self, other: object) -> bool:
		if not isinstance(other, Import):
			return NotImplemented
		return (self.name, self.src, self.kind) == (other.name, other.src, other.kind)

	@override
	def __hash__(self) -> int:
		return hash((self.name, self.src, self.kind))

	@override
	def __repr__(self) -> str:
		parts = [f"name={self.name!r}", f"src={self.src!r}"]
		if self.kind != "named":
			parts.append(f"kind={self.kind!r}")
		if self.prop:
			parts.append(f"prop={self.prop!r}")
		return f"Import({', '.join(parts)})"


def registered_imports() -> list[Import]:
	"""Get all registered imports."""
	return list(IMPORT_REGISTRY)


def clear_import_registry() -> None:
	"""Clear the import registry."""
	IMPORT_REGISTRY.clear()


# =============================================================================
# js_import decorator/function
# =============================================================================


@overload
def js_import(
	name: str, src: str, *, is_default: bool = False
) -> Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	"Import a JS function for use in `@javascript` functions"
	...


@overload
def js_import(name: str, src: str, type_: type[T], *, is_default: bool = False) -> T:
	"Import a JS value for use in `@javascript` functions"
	...


def js_import(
	name: str, src: str, type_: type[T] | None = None, *, is_default: bool = False
) -> T | Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	imp = Import.default(name, src) if is_default else Import(name, src)

	if type_ is not None:
		return imp  # pyright: ignore[reportReturnType]

	def decorator(fn: Callable[[*Args], R]) -> Callable[[*Args], R]:
		return imp  # pyright: ignore[reportReturnType]

	return decorator
