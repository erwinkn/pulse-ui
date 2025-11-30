"""Unified JS import system for javascript_v2."""

from collections.abc import Callable, Sequence
from typing import ClassVar, TypeAlias, TypeVar, TypeVarTuple, overload, override

from pulse.javascript_v2.ids import generate_id

T = TypeVar("T")
Args = TypeVarTuple("Args")
R = TypeVar("R")

# Registry key: (name, src, is_default)
# - Named imports: (name, src, False)
# - Default/side-effect imports: ("", src, is_default) - dedupe by src only
_ImportKey: TypeAlias = tuple[str, str, bool]
_REGISTRY: dict[_ImportKey, "Import"] = {}


class Import:
	"""Universal import descriptor.

	Import identity is determined by (name, src, is_default):
	- Named imports: unique by (name, src)
	- Default imports: unique by src (name is the local binding)
	- Side-effect imports: unique by src (name is empty)

	When two Import objects reference the same underlying import, they share
	the same ID, allowing multiple Import objects to target different properties
	of the same import.

	Examples:
		# Named import: import { foo } from "./module"
		foo = Import("foo", "./module")

		# Default import: import React from "react"
		React = Import("React", "react", is_default=True)

		# Type-only import: import type { Foo } from "./types"
		Foo = Import("Foo", "./types", is_type_only=True)

		# Side-effect import: import "./styles.css"
		Import.side_effect("./styles.css")

		# Access a property of an import
		foo_bar = foo.with_prop("bar")  # foo.bar, shares same ID as foo
	"""

	__slots__: ClassVar[tuple[str, ...]] = (
		"name",
		"src",
		"is_default",
		"is_type_only",
		"before",
		"prop",
		"id",
	)

	name: str
	src: str
	is_default: bool
	is_type_only: bool
	before: tuple[str, ...]
	prop: str | None
	id: str

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		is_type_only: bool = False,
		before: Sequence[str] = (),
		prop: str | None = None,
	) -> None:
		self.name = name
		self.src = src
		self.is_default = is_default
		self.prop = prop

		before_tuple = tuple(before)

		# Dedupe key: for default/side-effect imports, only src matters
		key: _ImportKey = (
			("", src, is_default) if (is_default or name == "") else (name, src, False)
		)

		if key in _REGISTRY:
			existing = _REGISTRY[key]

			# Merge: type-only + regular = regular
			if existing.is_type_only and not is_type_only:
				existing.is_type_only = False

			# Merge: union of before constraints
			if before_tuple:
				merged_before = set(existing.before) | set(before_tuple)
				existing.before = tuple(sorted(merged_before))

			# Reuse ID and merged values
			self.id = existing.id
			self.is_type_only = existing.is_type_only
			self.before = existing.before
		else:
			# New import
			self.id = generate_id()
			self.is_type_only = is_type_only
			self.before = before_tuple
			_REGISTRY[key] = self

	@classmethod
	def default(
		cls,
		name: str,
		src: str,
		*,
		is_type_only: bool = False,
		before: Sequence[str] = (),
		prop: str | None = None,
	) -> "Import":
		"""Create a default import."""
		return cls(
			name,
			src,
			is_default=True,
			is_type_only=is_type_only,
			before=before,
			prop=prop,
		)

	@classmethod
	def named(
		cls,
		name: str,
		src: str,
		*,
		is_type_only: bool = False,
		before: Sequence[str] = (),
		prop: str | None = None,
	) -> "Import":
		"""Create a named import."""
		return cls(
			name,
			src,
			is_default=False,
			is_type_only=is_type_only,
			before=before,
			prop=prop,
		)

	@classmethod
	def type_(
		cls,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		before: Sequence[str] = (),
	) -> "Import":
		"""Create a type-only import."""
		return cls(name, src, is_default=is_default, is_type_only=True, before=before)

	@classmethod
	def side_effect(
		cls,
		src: str,
		before: Sequence[str] = (),
	) -> "Import":
		"""Create a side-effect import (e.g., CSS files). Unique by src only."""
		return cls("", src, is_default=False, is_type_only=False, before=before)

	@classmethod
	def css(
		cls,
		src: str,
		before: Sequence[str] = (),
	) -> "Import":
		"""Alias for side_effect, commonly used for CSS imports."""
		return cls.side_effect(src, before)

	@property
	def is_side_effect(self) -> bool:
		"""True if this is a side-effect only import (no bindings)."""
		return self.name == "" and not self.is_default

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

	def with_prop(self, prop: str) -> "Import":
		"""Create a new Import targeting a property of this import.

		The returned Import shares the same ID, so it references the same
		underlying JS import but accesses a different property.
		"""
		return Import(
			name=self.name,
			src=self.src,
			is_default=self.is_default,
			is_type_only=self.is_type_only,
			before=self.before,
			prop=prop,
		)

	@override
	def __repr__(self) -> str:
		parts = [f"name={self.name!r}", f"src={self.src!r}"]
		if self.is_default:
			parts.append("is_default=True")
		if self.is_type_only:
			parts.append("is_type_only=True")
		if self.prop:
			parts.append(f"prop={self.prop!r}")
		return f"Import({', '.join(parts)})"


def registered_imports() -> list[Import]:
	"""Get all registered imports."""
	return list(_REGISTRY.values())


def clear_import_registry() -> None:
	"""Clear the import registry."""
	_REGISTRY.clear()


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
	imp = Import.default(name, src) if is_default else Import.named(name, src)

	if type_ is not None:
		return imp  # pyright: ignore[reportReturnType]

	def decorator(fn: Callable[[*Args], R]) -> Callable[[*Args], R]:
		return imp  # pyright: ignore[reportReturnType]

	return decorator
