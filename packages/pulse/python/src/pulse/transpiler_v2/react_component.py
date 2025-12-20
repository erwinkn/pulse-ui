"""React component integration for transpiler_v2.

In v2, client React components are represented as Expr nodes (typically Import or Member).
The @react_component decorator wraps an expression in Ref(Jsx(expr)) to provide:

- A stable registry key via Ref
- JSX call semantics via Jsx (transpile to Element nodes)
- Type-safe Python call signature via .as_(fn)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, overload
from typing import Literal as Lit

from pulse.transpiler_v2.imports import Import, caller_file, is_relative_path
from pulse.transpiler_v2.nodes import Child, Element, Expr, Jsx, Ref

P = ParamSpec("P")


def default_signature(
	*children: Child, key: str | None = None, **props: Any
) -> Element: ...


# Overloaded decorator signatures
@overload
def react_component(
	name_or_expr: Expr,
	src: None = None,
	*,
	lazy: bool = False,
) -> Callable[[Callable[P, Element]], Callable[P, Element]]: ...


@overload
def react_component(
	name_or_expr: str | Lit["default"],
	src: str,
	*,
	is_default: bool = False,
	lazy: bool = False,
	version: str | None = None,
	before: tuple[str, ...] | list[str] = (),
) -> Callable[[Callable[P, Element]], Ref]: ...


def react_component(
	name_or_expr: str | Lit["default"] | Expr,
	src: str | None = None,
	*,
	is_default: bool = False,
	lazy: bool = False,
	version: str | None = None,
	before: tuple[str, ...] | list[str] = (),
) -> Callable[[Callable[P, Element]], Ref]:
	"""Decorator that uses the decorated function solely as a typed signature.

	Returns a Ref(Jsx(expr)) that:
	- Has a stable registry key (Ref)
	- Produces Element nodes when called in transpiled code (Jsx)
	- Preserves the function's type signature for type checkers

	Can be called with:
	- An Expr directly: @react_component(Member(my_import, "Header"), lazy=True)
	- Name + src: @react_component("Button", "@mantine/core")
	- name="default" shorthand: @react_component("default", "./MyComponent")

	Note: lazy=True is stored but not yet wired into codegen.
	"""
	# Create the expr here (before returning decorator) so relative path
	# resolution uses the correct caller frame (depth=2: here -> caller module)
	expr: Expr | None = None
	resolved_src: str | None = None
	use_fn_name = False

	if isinstance(name_or_expr, Expr):
		expr = name_or_expr
	elif src is not None:
		actual_is_default = is_default or name_or_expr == "default"
		kind = "default" if actual_is_default else "named"
		if name_or_expr == "default":
			# Will use function name, but need to resolve path now
			use_fn_name = True

			resolved_src = src
			if is_relative_path(src):
				caller = caller_file(depth=2)
				resolved_src = str((caller.parent / src).resolve())
		else:
			expr = Import(
				name_or_expr,
				src,
				kind=kind,
				version=version,
				before=before,
				_caller_depth=2,
			)

	def decorator(fn: Callable[P, Element]) -> Callable[P, Element]:
		nonlocal expr
		if use_fn_name and resolved_src is not None:
			# Create import with function name, using pre-resolved src
			expr = Import(
				fn.__name__,
				resolved_src,  # Already resolved, won't trigger path resolution
				kind="default",
				version=version,
				before=before,
			)
		if expr is None:
			raise ValueError("src is required when name is provided")

		# Wrap expr: Ref provides registry key, Jsx provides Element generation
		ref = Ref(Jsx(expr))

		# Note: lazy flag is not currently wired into codegen
		# Could store it via a separate side-registry if needed in future
		_ = lazy  # Suppress unused variable warning

		# Return the ref, typed as the decorated function for type checkers
		return ref.as_(type(fn))

	return decorator
