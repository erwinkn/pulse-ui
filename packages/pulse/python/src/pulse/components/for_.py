"""For loop component for mapping items to elements.

Provides a declarative way to render lists, similar to JavaScript's Array.map().
"""

from collections.abc import Callable, Iterable
from inspect import Parameter, signature
from typing import Any, TypeVar, overload

from pulse.transpiler.nodes import Call, Expr, Member, Node, transformer
from pulse.transpiler.transpiler import Transpiler

T = TypeVar("T")
TNode = TypeVar("TNode", bound=Node)


@transformer("For")
def emit_for(items: Any, fn: Any, *, ctx: "Transpiler") -> Expr:
	"""For(items, fn) -> items.map(fn)"""
	items_expr = ctx.emit_expr(items)
	fn_expr = ctx.emit_expr(fn)
	return Call(Member(items_expr, "map"), [fn_expr])


@overload
def For(items: Iterable[T], fn: Callable[[T], TNode]) -> list[TNode]: ...


@overload
def For(items: Iterable[T], fn: Callable[[T, int], TNode]) -> list[TNode]: ...


def For(items: Iterable[T], fn: Callable[..., TNode]) -> list[TNode]:
	"""Map items to elements, like JavaScript's Array.map().

	Iterates over `items` and calls `fn` for each one, returning a list of
	elements. The mapper function can accept either one argument (item) or
	two arguments (item, index).

	Args:
		items: Iterable of items to map over.
		fn: Mapper function that receives `(item)` or `(item, index)` and
			returns an Element. If `fn` has a `*args` parameter, it receives
			both item and index.

	Returns:
		A list of Elements, one for each item.

	Example:
		Single argument (item only)::

			ps.For(users, lambda user: UserCard(user=user, key=user.id))

		With index::

			ps.For(items, lambda item, i: ps.li(f"{i}: {item}", key=str(i)))

	Note:
		In transpiled `@javascript` code, `For` compiles to `.map()`.
	"""
	try:
		sig = signature(fn)
		has_varargs = any(
			p.kind == Parameter.VAR_POSITIONAL for p in sig.parameters.values()
		)
		num_positional = sum(
			1
			for p in sig.parameters.values()
			if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
		)
		accepts_two = has_varargs or num_positional >= 2
	except (ValueError, TypeError):
		# Builtins or callables without inspectable signature: default to single-arg
		accepts_two = False

	if accepts_two:
		return [fn(item, idx) for idx, item in enumerate(items)]
	return [fn(item) for item in items]


# Register For in EXPR_REGISTRY so it can be used in transpiled functions
Expr.register(For, emit_for)
