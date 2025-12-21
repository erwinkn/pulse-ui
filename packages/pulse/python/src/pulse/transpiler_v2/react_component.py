"""React component integration for transpiler_v2.

In v2, client React components are represented as Expr nodes (typically Import or Member).
The @react_component decorator wraps an expression in Jsx(expr) to provide:

- A stable registry key (from the underlying Import/Function)
- JSX call semantics via Jsx (transpile to Element nodes)
- Type-safe Python call signature via .as_(fn)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec

from pulse.transpiler_v2.nodes import Child, Element, Expr, Jsx

P = ParamSpec("P")


def default_signature(
	*children: Child, key: str | None = None, **props: Any
) -> Element: ...


def react_component(
	src: Expr,
	*,
	lazy: bool = False,
) -> Callable[[Callable[P, Element]], Callable[P, Element]]:
	"""Decorator that uses the decorated function solely as a typed signature.

	Returns a Jsx(expr) that:
	- Produces Element nodes when called in transpiled code (Jsx)
	- Preserves the function's type signature for type checkers

	Can be called with:
	- An Expr directly: @react_component(Member(my_import, "Header"), lazy=True)
	- Name + src: @react_component("Button", "@mantine/core")
	- name="default" shorthand: @react_component("default", "./MyComponent")

	Note: lazy=True is stored but not yet wired into codegen.
	"""

	def decorator(fn: Callable[P, Element]) -> Callable[P, Element]:
		# Wrap expr: Jsx provides Element generation
		jsx_wrapper = Jsx(src)

		# Note: lazy flag is not currently wired into codegen
		# Could store it via a separate side-registry if needed in future
		_ = lazy  # Suppress unused variable warning

		return jsx_wrapper

	return decorator
