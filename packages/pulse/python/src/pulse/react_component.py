# ============================================================================
# React Component Integration
# ============================================================================

from collections.abc import Callable
from contextvars import ContextVar
from typing import (
	Any,
	ClassVar,
	Generic,
	Literal,
	ParamSpec,
	TypeVar,
	cast,
	override,
)

from pulse.helpers import Sentinel
from pulse.reactive_extensions import unwrap
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import (
	JSExpr,
	JSMember,
	JSSpread,
	JSXElement,
	JSXProp,
	JSXSpreadProp,
)
from pulse.vdom import Child, Element, Node

T = TypeVar("T")
P = ParamSpec("P")
DEFAULT: Any = Sentinel("DEFAULT")


def default_signature(
	*children: Child, key: str | None = None, **props: Any
) -> Element: ...


# ----------------------------------------------------------------------------
# JSX transpilation helpers
# ----------------------------------------------------------------------------


def _build_jsx_props(kwargs: dict[str, Any]) -> list[JSXProp | JSXSpreadProp]:
	"""Build JSX props list from kwargs dict.

	Kwargs maps:
	- "propName" -> value for named props
	- "__spread_N" -> JSSpread(expr) for spread props
	"""
	props: list[JSXProp | JSXSpreadProp] = []
	for key, value in kwargs.items():
		if isinstance(value, JSSpread):
			props.append(JSXSpreadProp(value.expr))
		else:
			props.append(JSXProp(key, JSExpr.of(value)))
	return props


def _flatten_children(items: list[Any], out: list[JSExpr | JSXElement | str]) -> None:
	"""Flatten arrays and handle spreads in children list."""
	from pulse.transpiler.nodes import JSArray, JSString

	for it in items:
		# Convert raw values first
		it = JSExpr.of(it) if not isinstance(it, JSExpr) else it
		if isinstance(it, JSArray):
			_flatten_children(list(it.elements), out)
		elif isinstance(it, JSSpread):
			out.append(it.expr)
		elif isinstance(it, JSString):
			out.append(it.value)
		else:
			out.append(it)


class ReactComponentCallExpr(JSExpr):
	"""JSX call expression for a ReactComponent.

	Created when a ReactComponent is called with props. Supports subscripting
	to add children, producing the final JSXElement.
	"""

	is_jsx: ClassVar[bool] = True
	component: "ReactComponent[...]"
	props: tuple[JSXProp | JSXSpreadProp, ...]
	children: tuple[str | JSExpr | JSXElement, ...]

	def __init__(
		self,
		component: "ReactComponent[...]",
		props: tuple[JSXProp | JSXSpreadProp, ...],
		children: tuple[str | JSExpr | JSXElement, ...],
	) -> None:
		self.component = component
		self.props = props
		self.children = children

	@override
	def emit(self) -> str:
		return JSXElement(self.component, self.props, self.children).emit()

	@override
	def emit_subscript(self, indices: list[Any]) -> JSExpr:
		"""Handle Component(props...)[children] -> JSXElement."""
		extra_children: list[JSExpr | JSXElement | str] = []
		_flatten_children(indices, extra_children)
		all_children = list(self.children) + extra_children
		return JSXElement(self.component, self.props, all_children)

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Calling an already-called component is an error."""
		raise JSCompilationError(
			f"Cannot call <{self.component.name}> - already called. "
			+ "Use subscript for children: Component(props...)[children]"
		)


class ReactComponent(JSExpr, Generic[P]):
	"""
	A React component that can be used within the UI tree.
	Returns a function that creates mount point UITreeNode instances.

	Args:
	    name: Name of the component (or "default" for default export)
	    src: Module path to import the component from
	    is_default: True if this is a default export, else named export
	    prop: Optional property name to access the component from the imported object
	    lazy: Whether to lazy load the component
	    version: Optional npm semver constraint for this component's package
	    fn_signature: Function signature to parse for props
	    extra_imports: Additional imports to include (CSS files, etc.)

	Returns:
	    A function that creates Node instances with mount point tags
	"""

	import_: Import
	fn_signature: Callable[P, Element]
	lazy: bool
	_prop: str | None  # Property access like AppShell.Header

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		prop: str | None = None,
		lazy: bool = False,
		version: str | None = None,
		fn_signature: Callable[P, Element] = default_signature,
		extra_imports: tuple[Import, ...] | list[Import] | None = None,
	):
		# Create the Import directly (prop is stored separately on ReactComponent)
		if is_default:
			self.import_ = Import.default(name, src)
		else:
			self.import_ = Import.named(name, src)
		self._prop = prop

		self.fn_signature = fn_signature
		self.lazy = lazy
		# Optional npm semver constraint for this component's package
		self.version: str | None = version
		# Additional imports to include in route where this component is used
		self.extra_imports: list[Import] = list(extra_imports or [])
		COMPONENT_REGISTRY.get().add(self)

	@override
	def emit(self) -> str:
		if self.prop:
			return JSMember(self.import_, self.prop).emit()
		return self.import_.emit()

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Handle Component(props...) -> ReactComponentCallExpr."""
		props_list = _build_jsx_props(kwargs)
		children_list: list[JSExpr | JSXElement | str] = []
		_flatten_children(args, children_list)
		return ReactComponentCallExpr(self, tuple(props_list), tuple(children_list))

	@override
	def emit_subscript(self, indices: list[Any]) -> JSExpr:
		"""Direct subscript on ReactComponent is not allowed.

		Use Component(props...)[children] instead of Component[children].
		"""
		raise JSCompilationError(
			f"Cannot subscript ReactComponent '{self.name}' directly. "
			+ "Use Component(props...)[children] or Component()[children] instead."
		)

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
	def prop(self) -> str | None:
		return self._prop

	@property
	def expr(self) -> str:
		"""Expression for the component in the registry and VDOM tags.

		Uses the import's js_name (with unique ID suffix) to match the
		unified registry on the client side.
		"""
		if self.prop:
			return f"{self.import_.js_name}.{self.prop}"
		return self.import_.js_name

	@override
	def __repr__(self) -> str:
		default_part = ", default=True" if self.is_default else ""
		prop_part = f", prop='{self.prop}'" if self.prop else ""
		lazy_part = ", lazy=True" if self.lazy else ""
		return f"ReactComponent(name='{self.name}', src='{self.src}'{prop_part}{default_part}{lazy_part})"

	@override
	def __call__(self, *children: P.args, **props: P.kwargs) -> Node:  # pyright: ignore[reportIncompatibleMethodOverride]
		key = props.get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")
		# Remove 'key' from props as it's handled separately
		real_props = {k: unwrap(v) for k, v in props.items() if k != "key"}

		return Node(
			tag=f"$${self.expr}",
			key=key,
			props=real_props or None,
			children=cast(tuple[Child], children),
		)


class ComponentRegistry:
	"""A registry for React components that can be used as a context manager."""

	_token: Any

	def __init__(self):
		self.components: list[ReactComponent[...]] = []
		self._token = None

	def add(self, component: ReactComponent[...]):
		"""Adds a component to the registry."""
		self.components.append(component)

	def clear(self):
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
	"component_registry",
	default=ComponentRegistry(),  # noqa: B039
)


def registered_react_components():
	"""Get all registered React components."""
	return COMPONENT_REGISTRY.get().components


# ----------------------------------------------------------------------------
# Public decorator: define a wrapped React component from a Python function
# ----------------------------------------------------------------------------


def react_component(
	name: str | Literal["default"],
	src: str,
	*,
	prop: str | None = None,
	is_default: bool = False,
	lazy: bool = False,
	version: str | None = None,
	extra_imports: list[Import] | None = None,
) -> Callable[[Callable[P, None] | Callable[P, Element]], ReactComponent[P]]:
	"""
	Decorator to define a React component wrapper. The decorated function is
	passed to `ReactComponent`, which parses and validates its signature.

	Args:
	    tag: Name of the component (or "default" for default export)
	    import_: Module path to import the component from
	    property: Optional property name to access the component from the imported object
	    is_default: True if this is a default export, else named export
	    lazy: Whether to lazy load the component
	"""

	def decorator(fn: Callable[P, None] | Callable[P, Element]) -> ReactComponent[P]:
		return ReactComponent(
			name=name,
			src=src,
			prop=prop,
			is_default=is_default,
			lazy=lazy,
			version=version,
			fn_signature=fn,
			extra_imports=extra_imports,
		)

	return decorator
