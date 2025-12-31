from collections.abc import Callable, Iterable
from inspect import Parameter, signature
from typing import TypeVar, overload

from pulse.transpiler.nodes import Element

T = TypeVar("T")


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
