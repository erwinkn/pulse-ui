"""JSX expression helpers for transpilation.

This module provides utilities for building JSX elements from Python function calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, override

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.nodes import (
	JSExpr,
	JSSpread,
	JSString,
	JSXElement,
	JSXProp,
	JSXSpreadProp,
)


def build_jsx_props(kwargs: dict[str, Any]) -> list[JSXProp | JSXSpreadProp]:
	"""Build JSX props list from kwargs dict.

	Kwargs maps:
	- "propName" -> value for named props
	- "$spread{N}" -> JSSpread(expr) for spread props

	Dict order is preserved, so iteration order matches source order.
	"""
	props: list[JSXProp | JSXSpreadProp] = []

	for key, value in kwargs.items():
		if isinstance(value, JSSpread):
			# Spread prop: {...expr}
			props.append(JSXSpreadProp(value.expr))
		else:
			# Named prop - convert to JSExpr
			props.append(JSXProp(key, JSExpr.of(value)))

	return props


def convert_jsx_child(item: Any) -> JSExpr | JSXElement | str:
	"""Convert a single child item for JSX."""
	expr = JSExpr.of(item) if not isinstance(item, JSExpr) else item
	if isinstance(expr, JSSpread):
		# Spread children: pass the inner expression; React handles arrays
		return expr.expr
	if isinstance(expr, JSString):
		# Unwrap strings for cleaner JSX output: "Hello" -> Hello
		return expr.value
	return expr


@dataclass
class JSXCallExpr(JSExpr):
	"""Expression representing a called component/tag with props (but possibly more children).

	When subscripted, adds children to produce the final JSXElement.
	Calling again is an error (can't call an element).
	"""

	tag: str | JSExpr
	props: Sequence[JSXProp | JSXSpreadProp] = field(default_factory=tuple)
	children: Sequence[str | JSExpr | JSXElement] = field(default_factory=tuple)
	is_jsx: ClassVar[bool] = True

	@override
	def emit(self) -> str:
		# Emit as final JSXElement
		return JSXElement(self.tag, self.props, self.children).emit()

	@override
	def emit_subscript(self, indices: list[Any]) -> JSExpr:
		"""Handle Component(props...)[children] -> JSXElement."""
		if self.children:
			tag_str = self.tag if isinstance(self.tag, str) else "<component>"
			raise JSCompilationError(
				f"<{tag_str}> already has children from call args. "
				+ "Use either Component(*children) or Component()[children], not both."
			)
		children = [convert_jsx_child(c) for c in indices]
		return JSXElement(self.tag, self.props, children)

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Calling an already-called component is an error."""
		tag_str = self.tag if isinstance(self.tag, str) else "<component>"
		raise JSCompilationError(
			f"Cannot call JSX element <{tag_str}> - already called. "
			+ "Use subscript for children: Component(props...)[children]"
		)
