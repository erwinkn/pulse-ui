"""React component integration for transpiler_v2.

In v2, client React components are represented as JSX imports (`Import(..., jsx=True)`).
This module provides a thin, typed wrapper around such an import:

- Adds a useful Python call signature via `ParamSpec` (for authoring ergonomics).
- Tracks `lazy` as a codegen hint (NOT part of the VDOM wire format).
- Calling the wrapper produces a `nodes.Element` mount point (`tag="$$<id>"`).
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, Generic, Literal, ParamSpec, cast, override

from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import Child, Element, Expr, Prop, Value
from pulse.transpiler_v2.transpiler import Transpiler

P = ParamSpec("P")


def default_signature(
	*children: Child, key: str | None = None, **props: Any
) -> Element: ...


def _normalize_prop(value: Any) -> Prop:
	# Keep Expr as-is
	if isinstance(value, Expr):
		return value
	# Fast-path for primitives supported by v2 nodes
	if value is None or isinstance(value, (bool, int, float, str)):
		return cast(Prop, value)
	# Fallback: wrap as a Value() so it can be emitted/serialized intentionally
	return Value(value)


class ReactComponent(Expr, Generic[P]):
	"""Typed wrapper around a JSX `Import` that produces mount-point Elements."""

	import_: Import
	fn_signature: Callable[P, Element]
	lazy: bool

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		lazy: bool = False,
		fn_signature: Callable[P, Element] = default_signature,
		before: tuple[str, ...] | list[str] = (),
	) -> None:
		# Wrap an Import in JSX mode (call -> Element in transpile context)
		self.import_ = Import(name, src, is_default=is_default, jsx=True, before=before)
		self.fn_signature = fn_signature
		self.lazy = lazy
		COMPONENT_REGISTRY.get().add(self)

	@property
	def name(self) -> str:
		return self.import_.name

	@property
	def src(self) -> str:
		return self.import_.src

	@property
	def is_default(self) -> bool:
		return self.import_.is_default

	@property
	def key(self) -> str:
		"""Registry key / mount-point identifier (without the '$$' prefix)."""
		return self.import_.js_name

	@override
	def emit(self, out: list[str]) -> None:
		# As an Expr, the component evaluates to its imported identifier.
		self.import_.emit(out)

	@override
	def transpile_call(
		self, args: list[ast.expr], kwargs: dict[str, ast.expr], ctx: Transpiler
	) -> Expr:
		# Delegate to Import's JSX call handling.
		return self.import_.transpile_call(args, kwargs, ctx)

	@override
	def __call__(  # pyright: ignore[reportIncompatibleMethodOverride]
		self, *children: P.args, **props: P.kwargs
	) -> Element:
		"""Create a mount-point Element for this client component."""
		key = cast(Any, props).get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")

		real_props: dict[str, Prop] = {}
		for k, v in cast(dict[str, Any], props).items():
			if k == "key":
				continue
			real_props[k] = _normalize_prop(v)

		return Element(
			tag=f"$${self.key}",
			props=real_props or None,
			children=cast(tuple[Child, ...], children) or None,
			key=key,
		)


class ComponentRegistry:
	"""Registry for ReactComponent instances (used by codegen tooling)."""

	_token: Any

	def __init__(self):
		self.components: list[ReactComponent[...]] = []
		self._token = None

	def add(self, component: ReactComponent[...]) -> None:
		self.components.append(component)

	def clear(self) -> None:
		self.components.clear()

	def __enter__(self) -> "ComponentRegistry":
		self._token = COMPONENT_REGISTRY.set(self)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: Any,
	) -> Literal[False]:
		if self._token:
			COMPONENT_REGISTRY.reset(self._token)
			self._token = None
		return False


COMPONENT_REGISTRY: ContextVar[ComponentRegistry] = ContextVar(
	"component_registry_v2",
	default=ComponentRegistry(),  # noqa: B039
)


def registered_react_components() -> list[ReactComponent[...]]:
	return COMPONENT_REGISTRY.get().components


def react_component(
	name: str | Literal["default"],
	src: str,
	*,
	is_default: bool = False,
	lazy: bool = False,
	before: tuple[str, ...] | list[str] = (),
) -> Callable[[Callable[P, Element]], ReactComponent[P]]:
	"""Decorator that uses the decorated function solely as a typed signature."""

	# Support `name="default"` as a shorthand.
	if name == "default":
		is_default = True

	def decorator(fn: Callable[P, Element]) -> ReactComponent[P]:
		# If `name` was "default", fall back to the function name as local identifier.
		local_name = fn.__name__ if name == "default" else name
		return ReactComponent(
			name=local_name,
			src=src,
			is_default=is_default,
			lazy=lazy,
			fn_signature=fn,
			before=before,
		)

	return decorator
