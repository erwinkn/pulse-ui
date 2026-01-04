"""React component integration for transpiler.

In v2, client React components are represented as Expr nodes (typically Import or Member).
The @react_component decorator wraps an expression in Jsx(expr) to provide:

- JSX call semantics via Jsx (transpile to Element nodes)
- Type-safe Python call signature via .as_(fn)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec

from pulse.transpiler.nodes import Element, Expr, Jsx, Node

P = ParamSpec("P")


def default_signature(
	*children: Node, key: str | None = None, **props: Any
) -> Element: ...


def react_component(expr: Expr):
	"""Decorator that uses the decorated function solely as a typed signature.

	Returns a Jsx(expr) that preserves the function's type signature for type
	checkers and produces Element nodes when called in transpiled code.

	For lazy loading, use Import(lazy=True) directly:
		LazyChart = Import("Chart", "./Chart", kind="default", lazy=True)
		React.lazy(LazyChart)  # LazyChart is already a factory
	"""

	def decorator(fn: Callable[P, Any]) -> Callable[P, Element]:
		if not isinstance(expr, Expr):
			raise TypeError("react_component expects an Expr")

		# Wrap expr: Jsx provides Element generation
		jsx_wrapper = expr if isinstance(expr, Jsx) else Jsx(expr)
		return jsx_wrapper

	return decorator
