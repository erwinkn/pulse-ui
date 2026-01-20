"""React component helpers for Python API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, overload

from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element, Expr, Jsx, Node

P = ParamSpec("P")


def default_signature(
	*children: Node, key: str | None = None, **props: Any
) -> Element: ...


class ReactComponent(Jsx):
	"""JSX wrapper for React components with runtime call support."""

	def __init__(self, expr: Expr) -> None:
		if not isinstance(expr, Expr):
			raise TypeError("ReactComponent expects an Expr")
		if isinstance(expr, Jsx):
			expr = expr.expr
		super().__init__(expr)


@overload
def react_component(
	expr_or_name: Expr,
) -> Callable[[Callable[P, Any]], Callable[P, Element]]: ...


@overload
def react_component(
	expr_or_name: str, src: str, *, lazy: bool = False
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
			raise TypeError("react_component lazy only supported with (name, src)")
		component = ReactComponent(expr_or_name)
	elif isinstance(expr_or_name, str):
		if src is None:
			raise TypeError("react_component expects (name, src)")
		component = ReactComponent(Import(expr_or_name, src, lazy=lazy))
	else:
		raise TypeError("react_component expects an Expr or (name, src)")

	def decorator(fn: Callable[P, Any]) -> Callable[P, Element]:
		return component.as_(fn)

	return decorator


__all__ = ["ReactComponent", "react_component", "default_signature"]
