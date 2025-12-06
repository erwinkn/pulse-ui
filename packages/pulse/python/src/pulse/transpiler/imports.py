"""Unified JS import system for javascript_v2."""

import inspect
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import (
	ClassVar,
	TypeAlias,
	TypeVar,
	TypeVarTuple,
	overload,
	override,
)

from pulse.transpiler.context import is_interpreted_mode
from pulse.transpiler.ids import generate_id
from pulse.transpiler.nodes import JSExpr

T = TypeVar("T")
Args = TypeVarTuple("Args")
R = TypeVar("R")

# Registry key: (name, src, is_default)
# - Named imports: (name, src, False)
# - Default/side-effect imports: ("", src, is_default) - dedupe by src only
_ImportKey: TypeAlias = tuple[str, str, bool]
_REGISTRY: dict[_ImportKey, "Import"] = {}


def _caller_file(depth: int = 2) -> Path:
	"""Get the file path of the caller.

	Args:
		depth: How many frames to go back (2 = caller of the function that calls this)
	"""
	frame = inspect.currentframe()
	try:
		# Walk up the call stack
		for _ in range(depth):
			if frame is None:
				raise RuntimeError("Cannot determine caller frame")
			frame = frame.f_back
		if frame is None:
			raise RuntimeError("Cannot determine caller frame")
		return Path(frame.f_code.co_filename).resolve()
	finally:
		del frame


def _is_local_css_path(path: str) -> bool:
	"""Check if a CSS path refers to a local file vs a package import.

	Local paths:
	- Start with './' or '../' (relative)
	- Start with '/' (absolute)
	- Don't start with '@' (scoped npm package)
	- Don't look like a bare module specifier

	Package imports:
	- Start with '@' (e.g., '@mantine/core/styles.css')
	- Bare specifiers (e.g., 'some-package/styles.css')
	"""
	# Relative paths are local
	if path.startswith("./") or path.startswith("../"):
		return True
	# Absolute paths are local
	if path.startswith("/"):
		return True
	# Scoped packages
	if path.startswith("@"):
		return False
	# If it contains no slashes, it could be a local file in current dir
	# But without './' prefix, treat bare names as package imports for safety
	# Exception: if it ends with .css and doesn't look like a package
	if "/" not in path and path.endswith(".css"):
		# Ambiguous - could be local or package. Require explicit ./
		return False
	# Everything else (bare specifiers with paths) are package imports
	return False


class Import(JSExpr):
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

		# CSS module import with class access
		styles = Import.css_module("./styles.module.css", relative=True)
		styles.container  # Returns JSMember for 'container' class
	"""

	__slots__ = (  # pyright: ignore[reportUnannotatedClassAttribute]
		"name",
		"src",
		"is_default",
		"is_namespace",
		"is_type_only",
		"before",
		"id",
		"source_path",
	)

	is_primary: ClassVar[bool] = True

	name: str
	src: str
	is_default: bool
	is_namespace: bool
	is_type_only: bool
	before: tuple[str, ...]
	id: str
	source_path: Path | None  # For local CSS files that need to be copied

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		is_namespace: bool = False,
		is_type_only: bool = False,
		before: Sequence[str] = (),
		source_path: Path | None = None,
	) -> None:
		self.name = name
		self.src = src
		self.is_default = is_default
		self.is_namespace = is_namespace
		self.source_path = source_path

		before_tuple = tuple(before)

		# Dedupe key: for default/side-effect/namespace imports, only src matters
		key: _ImportKey = (
			("", src, is_default or is_namespace)
			if (is_default or is_namespace or name == "")
			else (name, src, False)
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
	) -> "Import":
		"""Create a default import."""
		return cls(
			name,
			src,
			is_default=True,
			is_type_only=is_type_only,
			before=before,
		)

	@classmethod
	def named(
		cls,
		name: str,
		src: str,
		*,
		is_type_only: bool = False,
		before: Sequence[str] = (),
	) -> "Import":
		"""Create a named import."""
		return cls(
			name,
			src,
			is_default=False,
			is_type_only=is_type_only,
			before=before,
		)

	@classmethod
	def namespace(
		cls,
		name: str,
		src: str,
		*,
		before: Sequence[str] = (),
	) -> "Import":
		"""Create a namespace import: import * as name from src."""
		return cls(
			name,
			src,
			is_namespace=True,
			before=before,
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

	@property
	def is_side_effect(self) -> bool:
		"""True if this is a side-effect only import (no bindings)."""
		return self.name == "" and not self.is_default

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this import."""
		return f"{self.name}_{self.id}"

	@override
	def emit(self) -> str:
		"""Emit JS code for this import.

		In normal mode: returns the unique JS name (e.g., "Button_1")
		In interpreted mode: returns a get_object call (e.g., "get_object('Button_1')")
		"""
		base = self.js_name
		if is_interpreted_mode():
			return f"get_object('{base}')"
		return base

	@override
	def __repr__(self) -> str:
		parts = [f"name={self.name!r}", f"src={self.src!r}"]
		if self.is_default:
			parts.append("is_default=True")
		if self.is_namespace:
			parts.append("is_namespace=True")
		if self.is_type_only:
			parts.append("is_type_only=True")
		if self.source_path:
			parts.append(f"source_path={self.source_path!r}")
		return f"Import({', '.join(parts)})"


class CssImport(Import):
	"""Import for CSS files (both local files and npm packages).

	For local files, tracks the source path and provides a generated filename
	for the output directory. For npm packages, acts as a regular import.

	Args:
		path: Path to CSS file. Can be:
			- Package path (e.g., "@mantine/core/styles.css")
			- Relative path with relative=True (e.g., "./global.css")
			- Absolute path (e.g., "/path/to/styles.css")
		module: If True, import as a CSS module (default export for class access).
			If False, import for side effects only (global styles).
			Automatically set to True if path ends with ".module.css".
		relative: If True, resolve path relative to the caller's file.
		before: List of import sources that should come after this import.

	Examples:
		# Side-effect CSS import (global styles)
		CssImport("@mantine/core/styles.css")

		# CSS module for class access (module=True auto-detected from .module.css)
		styles = CssImport("./styles.module.css", relative=True)
		styles.container  # Returns JSMember for 'container' class

		# Local CSS file (will be copied during codegen)
		CssImport("./global.css", relative=True)
	"""

	def __init__(
		self,
		path: str,
		*,
		module: bool = False,
		relative: bool = False,
		before: Sequence[str] = (),
	) -> None:
		# Auto-detect CSS modules based on filename
		if path.endswith(".module.css"):
			module = True

		source_path: Path | None = None
		import_src = path

		if relative:
			# Resolve relative to caller's file (depth=2: _caller_file -> __init__ -> caller)
			caller = _caller_file(depth=2)
			source_path = (caller.parent / Path(path)).resolve()
			if not source_path.exists():
				kind = "CSS module" if module else "CSS file"
				raise FileNotFoundError(
					f"{kind} '{path}' not found relative to {caller.parent}"
				)
			import_src = str(source_path)
		elif _is_local_css_path(path):
			# Absolute local path
			source_path = Path(path).resolve()
			if not source_path.exists():
				kind = "CSS module" if module else "CSS file"
				raise FileNotFoundError(f"{kind} '{path}' not found")
			import_src = str(source_path)

		# CSS modules are default imports with "css" name prefix
		# Side-effect imports have empty name and is_default=False
		name = "css" if module else ""
		is_default = module

		super().__init__(
			name,
			import_src,
			is_default=is_default,
			is_type_only=False,
			before=before,
			source_path=source_path,
		)

	@property
	def is_local(self) -> bool:
		"""True if this is a local CSS file (not an npm package)."""
		return self.source_path is not None

	@property
	def generated_filename(self) -> str | None:
		"""Generated filename for local CSS files, or None for package imports."""
		if self.source_path is None:
			return None
		if self.source_path.name.endswith(".module.css"):
			return f"css_{self.id}.module.css"
		return f"css_{self.id}.css"


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
def import_js(
	name: str, src: str, *, is_default: bool = False
) -> Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	"Import a JS function for use in `@javascript` functions"
	...


@overload
def import_js(name: str, src: str, type_: type[T], *, is_default: bool = False) -> T:
	"Import a JS value for use in `@javascript` functions"
	...


def import_js(
	name: str, src: str, type_: type[T] | None = None, *, is_default: bool = False
) -> T | Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	imp = Import.default(name, src) if is_default else Import.named(name, src)

	if type_ is not None:
		return imp  # pyright: ignore[reportReturnType]

	def decorator(fn: Callable[[*Args], R]) -> Callable[[*Args], R]:
		return imp  # pyright: ignore[reportReturnType]

	return decorator
