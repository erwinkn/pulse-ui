"""Component definition and VDOM node types for Pulse.

This module provides the core component abstraction for building Pulse UIs,
including the `@component` decorator and the `Component` class.
"""

from __future__ import annotations

from collections.abc import Callable
from inspect import Parameter, signature
from types import CodeType
from typing import Any, Generic, ParamSpec, TypeVar, cast, overload, override

from pulse.code_analysis import is_stub_function
from pulse.hooks.init import rewrite_init_blocks
from pulse.hot_reload.deps import compute_component_deps, get_unknown_deps
from pulse.hot_reload.signatures import compute_component_signature_data
from pulse.transpiler.nodes import (
	Children,
	Node,
	Primitive,
	PulseNode,
	flatten_children,
)
from pulse.transpiler.nodes import Element as Element
from pulse.transpiler.vdom import VDOMNode

P = ParamSpec("P")
_T = TypeVar("_T")

_COMPONENT_CODES: set[CodeType] = set()
COMPONENT_BY_ID: dict[str, "Component[Any]"] = {}
COMPONENT_ID_BY_CODE: dict[CodeType, str] = {}


def is_component_code(code: CodeType) -> bool:
	return code in _COMPONENT_CODES


class Component(Generic[P]):
	"""A callable wrapper that turns a function into a Pulse component.

	Component instances are created by the `@component` decorator. When called,
	they return a `PulseNode` that represents the component in the virtual DOM.

	Attributes:
		name: Display name of the component (defaults to function name).
		fn: The underlying render function (lazily initialized for stubs).

	Example:

	```python
	@ps.component
	def Card(title: str):
	    return ps.div(ps.h3(title))

	Card(title="Hello")  # Returns a PulseNode
	Card(title="Hello", key="card-1")  # With reconciliation key
	```
	"""

	_raw_fn: Callable[P, Any]
	_fn: Callable[P, Any] | None
	name: str
	_takes_children: bool | None
	component_id: str
	signature_hash: str | None
	signature: list[Any] | None
	deps: set[str]
	unknown_deps: bool

	def __init__(self, fn: Callable[P, Any], name: str | None = None) -> None:
		"""Initialize a Component.

		Args:
			fn: The function to wrap as a component.
			name: Custom display name. Defaults to the function's `__name__`.
		"""
		self._raw_fn = fn
		self.name = name or _infer_component_name(fn)
		self.component_id = _component_id(fn)
		self.signature, self.signature_hash = compute_component_signature_data(fn)
		self.deps = compute_component_deps(fn)
		self.unknown_deps = get_unknown_deps(fn)
		# Only lazy-init for stubs (avoid heavy work for JS module bindings)
		# Real components need immediate rewrite for early error detection
		if is_stub_function(fn):
			self._fn = None
			self._takes_children = None
		else:
			self._fn = rewrite_init_blocks(fn)
			self._takes_children = _takes_children(fn)
			_COMPONENT_CODES.add(self._fn.__code__)
			COMPONENT_ID_BY_CODE[self._fn.__code__] = self.component_id
		COMPONENT_BY_ID[self.component_id] = cast("Component[Any]", self)

	def refresh(self, fn: Callable[..., Any], name: str | None = None) -> None:
		"""Update component in place (used by hot reload)."""
		self._raw_fn = fn
		self.name = name or _infer_component_name(fn)
		self.signature, self.signature_hash = compute_component_signature_data(fn)
		self.deps = compute_component_deps(fn)
		self.unknown_deps = get_unknown_deps(fn)

		old_code = self._fn.__code__ if self._fn is not None else None
		new_code: CodeType | None = None
		if is_stub_function(fn):
			self._fn = None
			self._takes_children = None
		else:
			self._fn = rewrite_init_blocks(fn)
			self._takes_children = _takes_children(fn)
			new_code = self._fn.__code__
			_COMPONENT_CODES.add(new_code)
			COMPONENT_ID_BY_CODE[new_code] = self.component_id

		if old_code is not None and old_code is not new_code:
			_COMPONENT_CODES.discard(old_code)
			COMPONENT_ID_BY_CODE.pop(old_code, None)

	@property
	def fn(self) -> Callable[P, Any]:
		"""The render function (lazily initialized for stub functions)."""
		if self._fn is None:
			self._fn = rewrite_init_blocks(self._raw_fn)
			self._takes_children = _takes_children(self._raw_fn)
			_COMPONENT_CODES.add(self._fn.__code__)
			COMPONENT_ID_BY_CODE[self._fn.__code__] = self.component_id
		return self._fn

	@property
	def raw_fn(self) -> Callable[P, Any]:
		return self._raw_fn

	def __call__(self, *args: P.args, **kwargs: P.kwargs) -> PulseNode:
		"""Invoke the component to create a PulseNode.

		Args:
			*args: Positional arguments passed to the component function.
			**kwargs: Keyword arguments passed to the component function.
				The special `key` kwarg is used for reconciliation.

		Returns:
			A PulseNode representing this component invocation in the VDOM.

		Raises:
			ValueError: If `key` is provided but is not a string.
		"""
		key = kwargs.get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")

		# Access self.fn to trigger lazy init (sets _takes_children)
		_ = self.fn
		if self._takes_children is True and args:
			flattened = flatten_children(
				args,  # pyright: ignore[reportArgumentType]
				parent_name=f"<{self.name}>",
				warn_stacklevel=None,
			)
			args = tuple(flattened)  # pyright: ignore[reportAssignmentType]

		return PulseNode(
			fn=self.fn,
			args=args,
			kwargs=kwargs,
			key=key,
			name=self.name,
			component_id=self.component_id,
			signature_hash=self.signature_hash,
			signature=self.signature,
		)

	@override
	def __repr__(self) -> str:
		return f"Component(name={self.name!r}, fn={_callable_qualname(self._raw_fn)!r})"

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
	"""Decorator that creates a Pulse component from a function.

	Can be used with or without parentheses. The decorated function becomes
	callable and returns a `PulseNode` when invoked.

	Args:
		fn: Function to wrap as a component. When used as `@component` without
			parentheses, this is the decorated function.
		name: Custom component name for debugging/dev tools. Defaults to the
			function's `__name__`.

	Returns:
		A `Component` instance if `fn` is provided, otherwise a decorator.

	Example:

	Basic usage:

	```python
	@ps.component
	def Card(title: str):
	    return ps.div(ps.h3(title))
	```

	With custom name:

	```python
	@ps.component(name="MyCard")
	def card_impl(title: str):
	    return ps.div(ps.h3(title))
	```

	With children (use `*children` parameter):

	```python
	@ps.component
	def Container(*children):
	    return ps.div(*children, className="container")

	# Children can be passed via subscript syntax:
	Container()[
	    Card(title="First"),
	    Card(title="Second"),
	]
	```
	"""

	def decorator(fn: Callable[P, Any]) -> Component[P]:
		component_id = _component_id(fn)
		existing = COMPONENT_BY_ID.get(component_id)
		if existing is not None:
			updated = cast("Component[P]", existing)
			updated.refresh(fn, name)
			return updated
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


def _component_id(fn: Callable[..., Any]) -> str:
	mod = getattr(fn, "__module__", "<unknown>")
	qname = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
	return f"{mod}:{qname}"


__all__ = [
	"Node",
	"Children",
	"Component",
	"Element",
	"Primitive",
	"VDOMNode",
	"component",
	"is_component_code",
	"COMPONENT_BY_ID",
	"COMPONENT_ID_BY_CODE",
]
