"""Import with auto-registration for transpiler_v2."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import (
	Any,
	ParamSpec,
	TypeAlias,
	TypeVar,
	override,
)
from typing import Literal as Lit

from pulse.cli.packages import pick_more_specific
from pulse.transpiler_v2.id import next_id
from pulse.transpiler_v2.nodes import Call, Expr

_P = ParamSpec("_P")
_R = TypeVar("_R")

ImportKind: TypeAlias = Lit["named", "default", "namespace", "side_effect"]

# JS-like extensions to try when resolving imports without extension (ESM convention)
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts")


def caller_file(depth: int = 2) -> Path:
	"""Get the file path of the caller."""
	frame = inspect.currentframe()
	try:
		for _ in range(depth):
			if frame is None:
				raise RuntimeError("Could not determine caller file")
			frame = frame.f_back
		if frame is None:
			raise RuntimeError("Could not determine caller file")
		return Path(frame.f_code.co_filename)
	finally:
		del frame


def is_relative_path(path: str) -> bool:
	"""Check if path is a relative import (starts with ./ or ../)."""
	return path.startswith("./") or path.startswith("../")


def is_absolute_path(path: str) -> bool:
	"""Check if path is an absolute filesystem path."""
	return path.startswith("/")


def is_local_path(path: str) -> bool:
	"""Check if path is a local file path (relative or absolute)."""
	return is_relative_path(path) or is_absolute_path(path)


def resolve_js_file(base_path: Path) -> Path | None:
	"""Resolve a JS-like import path to an actual file.

	Follows ESM resolution order:
	1. Exact path (if has extension)
	2. Try JS extensions: .ts, .tsx, .js, .jsx, .mjs, .mts
	3. Try /index with each extension

	Returns None if no file is found.
	"""
	# If path already has an extension that exists, use it
	if base_path.suffix and base_path.exists():
		return base_path

	# If no extension, try JS-like extensions
	if not base_path.suffix:
		for ext in _JS_EXTENSIONS:
			candidate = base_path.with_suffix(ext)
			if candidate.exists():
				return candidate

		# Try /index with each extension
		for ext in _JS_EXTENSIONS:
			candidate = base_path / f"index{ext}"
			if candidate.exists():
				return candidate

	return None


def resolve_local_path(path: str, caller: Path | None = None) -> Path | None:
	"""Resolve a local import path to an actual file.

	For relative paths, resolves relative to caller.
	For absolute paths, uses the path directly.

	For paths without extensions, tries JS-like resolution.
	Falls back to the raw resolved path if the file doesn't exist
	(might be a generated file or future file).

	Returns None only for non-local paths or relative paths without a caller.
	"""
	if is_relative_path(path):
		if caller is None:
			return None
		base_path = (caller.parent / Path(path)).resolve()
	elif is_absolute_path(path):
		base_path = Path(path).resolve()
	else:
		return None

	# If the path has an extension, return it (even if it doesn't exist)
	if base_path.suffix:
		return base_path

	# Try JS-like resolution for existing files
	resolved = resolve_js_file(base_path)
	if resolved is not None:
		return resolved

	# Fallback: return the base path even if the file doesn't exist
	return base_path


# Registry key depends on kind:
# - named: (name, src, "named")
# - default/namespace/side_effect: ("", src, kind) - only one per src
_ImportKey: TypeAlias = tuple[str, str, str]
_IMPORT_REGISTRY: dict[_ImportKey, "Import"] = {}


def get_registered_imports() -> list["Import"]:
	"""Get all registered imports."""
	return list(_IMPORT_REGISTRY.values())


def clear_import_registry() -> None:
	"""Clear the import registry."""
	_IMPORT_REGISTRY.clear()


@dataclass(slots=True, init=False)
class Import(Expr):
	"""JS import that auto-registers and dedupes.

	An Expr that emits as its unique identifier (e.g., useState_1).
	Overrides transpile_call for JSX component behavior and transpile_getattr for
	member access.

	Examples:
		# Named import: import { useState } from "react"
		useState = Import("useState", "react")

		# Default import: import React from "react"
		React = Import("React", "react", kind="default")

		# Namespace import: import * as utils from "./utils"
		utils = Import("utils", "./utils", kind="namespace")

		# Side-effect import: import "./styles.css"
		Import("", "./styles.css", kind="side_effect")

		# Type-only import: import type { Props } from "./types"
		Props = Import("Props", "./types", is_type=True)

		# JSX component import - wrap in Jsx() to create elements
		Button = Jsx(Import("Button", "@mantine/core"))
		# Button("Click me", disabled=True) -> <Button_1 disabled={true}>Click me</Button_1>

		# Local file imports (relative or absolute paths)
		Import("", "./styles.css", kind="side_effect")  # Local CSS
		utils = Import("utils", "./utils", kind="namespace")  # Local JS (resolves extension)
		config = Import("config", "/absolute/path/config", kind="default")  # Absolute path
	"""

	name: str
	src: str
	kind: ImportKind
	is_type: bool
	before: tuple[str, ...]
	id: str
	version: str | None = None
	source_path: Path | None = (
		None  # Resolved local file path (for copying during codegen)
	)

	def __init__(
		self,
		name: str,
		src: str,
		*,
		kind: ImportKind | None = None,
		is_type: bool = False,
		version: str | None = None,
		before: tuple[str, ...] | list[str] = (),
		_caller_depth: int = 2,
	) -> None:
		# Auto-resolve local paths (relative or absolute) to actual files
		source_path: Path | None = None
		import_src = src

		if is_local_path(src):
			# Resolve to actual file (handles JS extension resolution)
			caller = caller_file(depth=_caller_depth) if is_relative_path(src) else None
			resolved = resolve_local_path(src, caller)
			if resolved is not None:
				source_path = resolved
				import_src = str(resolved)

		# Default kind to "named" if not specified
		if kind is None:
			kind = "named"

		self.name = name
		self.src = import_src
		self.kind = kind
		self.version = version
		self.source_path = source_path

		before_tuple = tuple(before) if isinstance(before, list) else before

		# Dedupe key: for named imports use (name, src, "named")
		# For default/namespace/side_effect, only one per src: ("", src, kind)
		if kind == "named":
			key: _ImportKey = (name, import_src, "named")
		else:
			key = ("", import_src, kind)

		if key in _IMPORT_REGISTRY:
			existing = _IMPORT_REGISTRY[key]

			# Merge: type-only + regular = regular
			if existing.is_type and not is_type:
				existing.is_type = False

			# Merge: union of before constraints
			if before_tuple:
				merged_before = set(existing.before) | set(before_tuple)
				existing.before = tuple(sorted(merged_before))

			# Merge: version
			existing.version = pick_more_specific(existing.version, version)

			# Reuse ID and merged values
			self.id = existing.id
			self.is_type = existing.is_type
			self.before = existing.before
			self.version = existing.version
		else:
			# New import
			self.id = next_id()
			self.is_type = is_type
			self.before = before_tuple
			_IMPORT_REGISTRY[key] = self

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this import."""
		return f"{self.name}_{self.id}"

	@property
	def is_local(self) -> bool:
		"""Check if this is a local file import (has resolved source_path)."""
		return self.source_path is not None

	# Convenience properties for kind checks
	@property
	def is_default(self) -> bool:
		return self.kind == "default"

	@property
	def is_namespace(self) -> bool:
		return self.kind == "namespace"

	@property
	def is_side_effect(self) -> bool:
		return self.kind == "side_effect"

	def asset_filename(self) -> str:
		"""Get the filename for this import when copied to assets folder.

		Uses the import ID for uniqueness and preserves the original extension.
		For JS-like files, uses the resolved extension.
		"""
		if self.source_path is None:
			raise ValueError("Cannot get asset filename for non-local import")
		stem = self.source_path.stem
		suffix = self.source_path.suffix
		return f"{stem}_{self.id}{suffix}"

	# -------------------------------------------------------------------------
	# Expr.emit: outputs the unique identifier
	# -------------------------------------------------------------------------

	@override
	def emit(self, out: list[str]) -> None:
		"""Emit this import as its unique JS identifier."""
		out.append(self.js_name)

	# -------------------------------------------------------------------------
	# Python dunder methods: allow natural syntax in @javascript functions
	# -------------------------------------------------------------------------

	# Overloads for __call__:
	# 1. Decorator usage: @Import(...) def fn(...) -> returns fn's type
	# 2. Expression usage: Import(...)(...) -> returns Call

	@override
	def __call__(self, *args: Any, **kwargs: Any) -> "Call":
		"""Allow calling Import objects in Python code.

		Returns a Call expression.
		"""
		return Expr.__call__(self, *args, **kwargs)
