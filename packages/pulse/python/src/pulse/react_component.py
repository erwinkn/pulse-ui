"""React component helpers for Python API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, overload

from pulse.js.react import lazy as react_lazy
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element, Expr, Jsx, Node

P = ParamSpec("P")


def default_signature(
	*children: Node, key: str | None = None, **props: Any
) -> Element: ...


class ReactComponent(Jsx):
	"""JSX wrapper for React components with runtime call support."""

	def __init__(self, expr_or_src: Expr | str, *, lazy: bool = False) -> None:
		if isinstance(expr_or_src, str):
			if lazy:
				expr: Expr = react_lazy(Import(expr_or_src, lazy=True))
			else:
				expr = Import(expr_or_src)
		else:
			if lazy:
				raise TypeError(
					"ReactComponent lazy only supported with a source string"
				)
			expr = expr_or_src
		if not isinstance(expr, Expr):
			raise TypeError("ReactComponent expects an Expr or source string")
		if isinstance(expr, Jsx):
			expr = expr.expr
		super().__init__(expr)


@overload
def react_component(
	expr_or_name: Expr,
) -> Callable[[Callable[P, Any]], Callable[P, Element]]: ...


@overload
def react_component(
	expr_or_name: str,
	src: str | None = None,
	*,
	lazy: bool = False,
) -> Callable[[Callable[P, Any]], Callable[P, Element]]: ...


def react_component(
	expr_or_name: Expr | str,
	src: str | None = None,
	*,
	lazy: bool = False,
) -> Callable[[Callable[P, Any]], Callable[P, Element]]:
	"""Decorator for typed React component bindings."""
	if isinstance(expr_or_name, Expr):
		if src is not None:
			raise TypeError("react_component expects (expr) or (name, src)")
		if lazy:
			raise TypeError("react_component lazy only supported with string inputs")
		component = ReactComponent(expr_or_name)
	elif isinstance(expr_or_name, str):
		if src is None:
			component = ReactComponent(expr_or_name, lazy=lazy)
		else:
			imp = Import(expr_or_name, src, lazy=lazy)
			if lazy:
				component = ReactComponent(react_lazy(imp))
			else:
				component = ReactComponent(imp)
	else:
		raise TypeError("react_component expects an Expr or (name, src)")

	def decorator(fn: Callable[P, Any]) -> Callable[P, Element]:
		return component.as_(fn)

	return decorator


__all__ = ["ReactComponent", "react_component", "default_signature"]
