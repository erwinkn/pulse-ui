from collections.abc import Callable, Iterable
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Any, TypeVar, overload

from pulse.transpiler.nodes import Call, Element, Expr, Member, transformer

if TYPE_CHECKING:
	from pulse.transpiler.transpiler import Transpiler

T = TypeVar("T")


@transformer("For")
def _emit_for(items: Any, fn: Any, *, ctx: "Transpiler") -> Expr:
	"""For(items, fn) -> items.map(fn)"""
	items_expr = ctx.emit_expr(items)
	fn_expr = ctx.emit_expr(fn)
	return Call(Member(items_expr, "map"), [fn_expr])


@overload
def For(items: Iterable[T], fn: Callable[[T], Element]) -> list[Element]: ...


@overload
def For(items: Iterable[T], fn: Callable[[T, int], Element]) -> list[Element]: ...


def For(items: Iterable[T], fn: Callable[..., Element]) -> list[Element]:
	"""Map items to elements, passing `(item)` or `(item, index)`.

	The callable `fn` may accept either a single positional argument (the item)
	or two positional arguments (the item and its index), similar to JavaScript's
	Array.map. If `fn` declares `*args`, it will receive `(item, index)`.
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
Expr.register(For, _emit_for)
