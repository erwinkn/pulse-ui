from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from inspect import Parameter, signature
from typing import Any, Generic, ParamSpec, TypeAlias, TypeVar, overload, override

from pulse.hooks.init import rewrite_init_blocks
from pulse.transpiler_v2.nodes import Element as Element
from pulse.transpiler_v2.nodes import (
	Node,
	Primitive,
	PulseNode,
	_flatten_children,
)
from pulse.transpiler_v2.vdom import VDOMNode

P = ParamSpec("P")
_T = TypeVar("_T")

Children: TypeAlias = Sequence[Node | Iterable[Node]]


class Component(Generic[P]):
	fn: Callable[P, Any]
	name: str
	_takes_children: bool

	def __init__(self, fn: Callable[P, Any], name: str | None = None) -> None:
		self.fn = rewrite_init_blocks(fn)
		self.name = name or _infer_component_name(fn)
		self._takes_children = _takes_children(fn)

	def __call__(self, *args: P.args, **kwargs: P.kwargs) -> PulseNode:
		key = kwargs.get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")

		if self._takes_children and args:
			flattened = _flatten_children(
				args,  # type: ignore[arg-type]
				parent_name=f"<{self.name}>",
				warn_stacklevel=4,
			)
			args = tuple(flattened)  # type: ignore[assignment]

		return PulseNode(fn=self.fn, args=args, kwargs=kwargs, key=key, name=self.name)

	@override
	def __repr__(self) -> str:
		return f"Component(name={self.name!r}, fn={_callable_qualname(self.fn)!r})"

	@override
	def __str__(self) -> str:
		return self.name


@overload
def component(fn: Callable[P, Any]) -> Component[P]: ...


@overload
def component(
	fn: None = None, *, name: str | None = None
) -> Callable[[Callable[P, Any]], Component[P]]: ...


# The explicit return type is necessary for the type checker to be happy
def component(
	fn: Callable[P, Any] | None = None, *, name: str | None = None
) -> Component[P] | Callable[[Callable[P, Any]], Component[P]]:
	def decorator(fn: Callable[P, Any]) -> Component[P]:
		return Component(fn, name)

	if fn is not None:
		return decorator(fn)
	return decorator


def _takes_children(fn: Callable[..., Any]) -> bool:
	try:
		sig = signature(fn)
	except (ValueError, TypeError):
		return False
	for p in sig.parameters.values():
		if p.kind == Parameter.VAR_POSITIONAL and p.name == "children":
			return True
	return False


# ----------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------


def _infer_component_name(fn: Callable[..., Any]) -> str:
	name = getattr(fn, "__name__", None)
	if name:
		return name
	return "Component"


def _callable_qualname(fn: Callable[..., Any]) -> str:
	mod = getattr(fn, "__module__", "<unknown>")
	qname = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
	return f"{mod}.{qname}"


__all__ = [
	"Node",
	"Children",
	"Component",
	"Element",
	"Primitive",
	"VDOMNode",
	"component",
]
