"""Import with auto-registration for transpiler_v2."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TypeAlias, override

from pulse.transpiler_v2.errors import TranspileError
from pulse.transpiler_v2.nodes import (
	Call,
	Child,
	Element,
	Expr,
	Literal,
	Member,
	Prop,
)
from pulse.transpiler_v2.transpiler import Transpiler

# Registry key: (name, src, is_default)
# - Named imports: (name, src, False)
# - Default imports: ("", src, True)
_ImportKey: TypeAlias = tuple[str, str, bool]
_IMPORT_REGISTRY: dict[_ImportKey, "Import"] = {}
_import_id_counter: int = 0


def _next_import_id() -> str:
	"""Generate a unique import ID."""
	global _import_id_counter
	_import_id_counter += 1
	return str(_import_id_counter)


def get_registered_imports() -> list["Import"]:
	"""Get all registered imports."""
	return list(_IMPORT_REGISTRY.values())


def clear_import_registry() -> None:
	"""Clear the import registry and reset ID counter."""
	global _import_id_counter
	_IMPORT_REGISTRY.clear()
	_import_id_counter = 0


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
		React = Import("React", "react", is_default=True)

		# Type-only import: import type { Props } from "./types"
		Props = Import("Props", "./types", is_type=True)

		# JSX component import - callable to create elements
		Button = Import("Button", "@mantine/core", jsx=True)
		# Button("Click me", disabled=True) -> <Button_1 disabled={true}>Click me</Button_1>
	"""

	name: str
	src: str
	is_default: bool
	is_type: bool
	jsx: bool
	before: tuple[str, ...]
	id: str

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		is_type: bool = False,
		jsx: bool = False,
		before: tuple[str, ...] | list[str] = (),
	) -> None:
		self.name = name
		self.src = src
		self.is_default = is_default
		self.jsx = jsx

		before_tuple = tuple(before) if isinstance(before, list) else before

		# Dedupe key: for default imports, only src matters
		key: _ImportKey = ("", src, True) if is_default else (name, src, False)

		if key in _IMPORT_REGISTRY:
			existing = _IMPORT_REGISTRY[key]

			# Merge: type-only + regular = regular
			if existing.is_type and not is_type:
				existing.is_type = False

			# Merge: union of before constraints
			if before_tuple:
				merged_before = set(existing.before) | set(before_tuple)
				existing.before = tuple(sorted(merged_before))

			# Reuse ID and merged values
			self.id = existing.id
			self.is_type = existing.is_type
			self.before = existing.before
		else:
			# New import
			self.id = _next_import_id()
			self.is_type = is_type
			self.before = before_tuple
			_IMPORT_REGISTRY[key] = self

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this import."""
		return f"{self.name}_{self.id}"

	# -------------------------------------------------------------------------
	# Expr.emit: outputs the unique identifier
	# -------------------------------------------------------------------------

	@override
	def emit(self, out: list[str]) -> None:
		"""Emit this import as its unique JS identifier."""
		out.append(self.js_name)

	# -------------------------------------------------------------------------
	# transpile_call: handles fn() syntax
	# -------------------------------------------------------------------------

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		"""Handle calls on this import.

		For jsx=True: produces Element with args as children, kwargs as props.
		For jsx=False: produces standard Call node.
		"""
		if not self.jsx:
			# Standard function call
			js_args = [ctx.emit_expr(a) for a in args]
			return Call(self, js_args)

		# JSX mode: positional args are children, kwargs are props
		children: list[Child] = []
		for a in args:
			children.append(ctx.emit_expr(a))

		props: dict[str, Prop] = {}
		key: str | None = None
		for k, v in kwargs.items():
			prop_value = ctx.emit_expr(v)
			if k == "key":
				# Extract key prop
				if isinstance(prop_value, Literal) and isinstance(
					prop_value.value, str
				):
					key = prop_value.value
				else:
					raise TranspileError("key prop must be a string literal")
			else:
				props[k] = prop_value

		return Element(
			tag=f"$${self.js_name}",
			props=props if props else None,
			children=children if children else None,
			key=key,
		)

	# -------------------------------------------------------------------------
	# transpile_getattr: handles import.attr syntax
	# -------------------------------------------------------------------------

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		"""Handle attribute access on this import.

		Produces Member(self, attr) - self already emits as the identifier.
		"""
		return Member(self, attr)

	# -------------------------------------------------------------------------
	# Python dunder methods: allow natural syntax in @javascript functions
	# -------------------------------------------------------------------------

	@override
	def __call__(self, *args: object, **kwargs: object) -> Call | Element:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Allow calling Import objects in Python code.

		Returns Call for regular imports, Element for JSX imports.
		The actual transpilation happens via transpile_call when the transpiler processes the AST.
		"""
		if self.jsx:
			return Element(tag=f"$${self.js_name}", props=None, children=None, key=None)
		return Call(self, [Expr.of(a) for a in args])
