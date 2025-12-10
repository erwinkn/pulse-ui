"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

import functools
import re
import warnings
from collections.abc import Callable, Iterable, Sequence
from inspect import Parameter, signature
from types import NoneType
from typing import (
	Any,
	Generic,
	Literal,
	NamedTuple,
	NotRequired,
	ParamSpec,
	TypeAlias,
	TypedDict,
	final,
	overload,
	override,
)

from pulse.env import env
from pulse.hooks.core import HookContext
from pulse.hooks.init import rewrite_init_blocks

# ============================================================================
# Core VDOM
# ============================================================================


class VDOMNode(TypedDict):
	tag: str
	key: NotRequired[str]
	props: NotRequired[dict[str, Any]]  # does not include callbacks
	children: "NotRequired[Sequence[VDOMNode | Primitive] | None]"


class Callback(NamedTuple):
	fn: Callable[..., Any]
	n_args: int


@final
class Node:
	__slots__ = (
		"tag",
		"props",
		"children",
		"allow_children",
		"key",
	)

	tag: str
	props: dict[str, Any] | None
	children: "list[Element] | None"
	allow_children: bool
	key: str | None

	def __init__(
		self,
		tag: str,
		props: dict[str, Any] | None | None = None,
		children: "Children | None" = None,
		key: str | None = None,
		allow_children: bool = True,
	):
		self.tag = tag
		self.props = props or None
		self.children = (
			_flatten_children(children, parent_name=f"<{self.tag}>")
			if children
			else None
		)
		self.allow_children = allow_children
		self.key = key or None
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")
		if not self.allow_children and children:
			clean_tag = clean_element_name(self.tag)
			raise ValueError(f"{clean_tag} cannot have children")

	# --- Pretty printing helpers -------------------------------------------------
	@override
	def __repr__(self) -> str:
		return (
			f"Node(tag={self.tag!r}, key={self.key!r}, props={_short_props(self.props)}, "
			f"children={_short_children(self.children)})"
		)

	def __getitem__(
		self,
		children_arg: "Child | tuple[Child, ...]",
	):
		"""Support indexing syntax: div()[children] or div()["text"]

		Children may include iterables (lists, generators) of nodes, which will
		be flattened during render.
		"""
		if self.children:
			raise ValueError(f"Node already has children: {self.children}")

		if isinstance(children_arg, tuple):
			new_children = list(children_arg)
		else:
			new_children = [children_arg]

		return Node(
			tag=self.tag,
			props=self.props,
			children=new_children,
			key=self.key,
			allow_children=self.allow_children,
		)

	@staticmethod
	def from_vdom(
		vdom: "VDOM",
		callbacks: "Callbacks | None" = None,
		*,
		path: str = "",
	) -> "Node | Primitive":
		"""Create a Node tree from a VDOM structure.

		- Primitive values are returned as-is
		- Callbacks can be reattached by providing both `callbacks` (the
		  callable registry) and `callback_props` (props per VDOM path)
		"""

		if isinstance(vdom, (str, int, float, bool, NoneType)):
			return vdom

		tag = vdom.get("tag")
		props = vdom.get("props") or {}
		key_value = vdom.get("key")

		callbacks = callbacks or {}
		prefix = f"{path}." if path else ""
		prop_names: list[str] = []
		for key in callbacks.keys():
			if path:
				if not key.startswith(prefix):
					continue
				remainder = key[len(prefix) :]
			else:
				remainder = key
			if "." in remainder:
				continue
			prop_names.append(remainder)
		if prop_names:
			props = props.copy()
			for name in prop_names:
				callback_key = f"{path}.{name}" if path else name
				callback = callbacks.get(callback_key)
				if not callback:
					raise ValueError(f"Missing callback '{callback_key}'")
				props[name] = callback.fn

		children_value: list[Element] | None = None
		raw_children = vdom.get("children")
		if raw_children is not None:
			children_value = []
			for idx, raw_child in enumerate(raw_children):
				child_path = f"{path}.{idx}" if path else str(idx)
				children_value.append(
					Node.from_vdom(
						raw_child,
						callbacks=callbacks,
						path=child_path,
					)
				)

		return Node(
			tag=tag,
			props=props or None,
			children=children_value,
			key=key_value,
		)


# ============================================================================
# Tag Definition Functions
# ============================================================================


# --- Components ---

P = ParamSpec("P")


class Component(Generic[P]):
	fn: "Callable[P, Element]"
	name: str
	_takes_children: bool

	def __init__(self, fn: "Callable[P, Element]", name: str | None = None) -> None:
		self.fn = fn
		self.name = name or _infer_component_name(fn)
		self._takes_children = _takes_children(fn)

	def __call__(self, *args: P.args, **kwargs: P.kwargs) -> "ComponentNode":
		key = kwargs.get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")

		# Flatten children if component accepts them via `*children` parameter
		if self._takes_children and args:
			flattened = _flatten_children(
				args,  # pyright: ignore[reportArgumentType]
				parent_name=f"<{self.name}>",
				warn_stacklevel=4,
			)
			args = tuple(flattened)  # pyright: ignore[reportAssignmentType]

		return ComponentNode(
			fn=self.fn,
			key=key,
			args=args,
			kwargs=kwargs,
			name=self.name,
			takes_children=self._takes_children,
		)

	@override
	def __repr__(self) -> str:
		return f"Component(name={self.name!r}, fn={_callable_qualname(self.fn)!r})"

	@override
	def __str__(self) -> str:
		return self.name


@final
class ComponentNode:
	__slots__ = (
		"fn",
		"args",
		"kwargs",
		"key",
		"name",
		"takes_children",
		"hooks",
		"contents",
	)

	fn: Callable[..., Any]
	args: tuple[Any, ...]
	kwargs: dict[str, Any]
	key: str | None
	name: str
	takes_children: bool
	hooks: HookContext
	contents: "Element | None"

	def __init__(
		self,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		name: str | None = None,
		key: str | None = None,
		takes_children: bool = True,
	) -> None:
		self.fn = fn
		self.args = args
		self.kwargs = kwargs
		self.key = key
		self.name = name or _infer_component_name(fn)
		self.takes_children = takes_children
		# Used for rendering
		self.contents = None
		self.hooks = HookContext()

	def __getitem__(self, children_arg: "Child | tuple[Child, ...]"):
		if not self.takes_children:
			raise TypeError(
				f"Component {self.name} does not accept children. "
				+ "Update the component signature to include '*children' to allow children."
			)
		if self.args:
			raise ValueError(
				f"Component {self.name} already received positional arguments. Pass all arguments as keyword arguments in order to pass children using brackets."
			)
		if not isinstance(children_arg, tuple):
			children_arg = (children_arg,)
		# Flatten children when component accepts them via `*children` parameter
		flattened_children = _flatten_children(
			children_arg, parent_name=f"<{self.name}>", warn_stacklevel=4
		)
		return ComponentNode(
			fn=self.fn,
			args=tuple(flattened_children),
			kwargs=self.kwargs,
			name=self.name,
			key=self.key,
			takes_children=self.takes_children,
		)

	@override
	def __repr__(self) -> str:
		return (
			f"ComponentNode(name={self.name!r}, key={self.key!r}, "
			f"args={_short_args(self.args)}, kwargs={_short_props(self.kwargs)})"
		)


@overload
def component(fn: "Callable[P, Element]") -> Component[P]: ...
@overload
def component(
	fn: None = None, *, name: str | None = None
) -> "Callable[[Callable[P, Element]], Component[P]]": ...


# The explicit return type is necessary for the type checker to be happy
def component(
	fn: "Callable[P, Element] | None" = None, *, name: str | None = None
) -> "Component[P] | Callable[[Callable[P, Element]], Component[P]]":
	def decorator(fn: Callable[P, Element]):
		rewritten = rewrite_init_blocks(fn)
		return Component(rewritten, name)

	if fn is not None:
		return decorator(fn)
	return decorator


Primitive = str | int | float | None
Element = Node | ComponentNode | Primitive
# A child can be an Element or any iterable yielding children (e.g., generators)
Child: TypeAlias = Element | Iterable[Element]
Children: TypeAlias = Sequence[Child]

Callbacks = dict[str, Callback]
VDOM: TypeAlias = VDOMNode | Primitive
Props = dict[str, Any]


# ============================================================================
# VDOM Operations (updates sent from server to client)
# ============================================================================


class ReplaceOperation(TypedDict):
	type: Literal["replace"]
	path: str
	data: VDOM


# This payload makes it easy for the client to rebuild an array of React nodes
# from the previous children array:
# - Allocate array of size N
# - For i in 0..N-1, check the following scenarios
#   - i matches the next index in `new` -> use provided tree
#   - i matches the next index in `reuse` -> reuse previous child
#   - otherwise, reuse the element at the same index
class ReconciliationOperation(TypedDict):
	type: Literal["reconciliation"]
	path: str
	N: int
	new: tuple[list[int], list[VDOM]]
	reuse: tuple[list[int], list[int]]


class UpdatePropsDelta(TypedDict, total=False):
	# Only send changed/new keys under `set` and removed keys under `remove`
	set: Props
	remove: list[str]


class UpdatePropsOperation(TypedDict):
	type: Literal["update_props"]
	path: str
	data: UpdatePropsDelta


class PathDelta(TypedDict, total=False):
	add: list[str]
	remove: list[str]


class UpdateCallbacksOperation(TypedDict):
	type: Literal["update_callbacks"]
	path: str
	data: PathDelta


class UpdateRenderPropsOperation(TypedDict):
	type: Literal["update_render_props"]
	path: str
	data: PathDelta


class UpdateJsExprPathsOperation(TypedDict):
	type: Literal["update_jsexpr_paths"]
	path: str
	data: PathDelta


VDOMOperation: TypeAlias = (
	ReplaceOperation
	| UpdatePropsOperation
	| ReconciliationOperation
	| UpdateCallbacksOperation
	| UpdateRenderPropsOperation
	| UpdateJsExprPathsOperation
)


# ----------------------------------------------------------------------------
# Sanitization heuristics
# ----------------------------------------------------------------------------


def _flatten_children(
	children: Children, *, parent_name: str, warn_stacklevel: int = 5
) -> list[Element]:
	"""Flatten children, switching between prod and dev implementations."""
	if env.pulse_env == "dev":
		return _flatten_children_dev(
			children, parent_name=parent_name, warn_stacklevel=warn_stacklevel
		)
	return _flatten_children_prod(children)


def _flatten_children_prod(children: Children) -> list[Element]:
	"""Flatten children (production mode - no checks)."""
	flat: list[Element] = []

	def visit(item: Child) -> None:
		if isinstance(item, Iterable) and not isinstance(item, str):
			for sub in item:
				visit(sub)
		else:
			flat.append(item)

	for child in children:
		visit(child)

	return flat


def _flatten_children_dev(
	children: Children, *, parent_name: str, warn_stacklevel: int = 5
) -> list[Element]:
	"""Flatten children and emit warnings for unkeyed iterables (dev mode only).

	Args:
		children: The children sequence to flatten.
		parent_name: Name of the parent element for error messages.
		warn_stacklevel: Stack level for warnings. Adjust based on call site:
			- 5 for Node.__init__ via tag factory (user -> tag factory -> Node.__init__ -> _flatten_children -> visit -> warn)
			- 4 for ComponentNode.__getitem__ or Component.__call__ (user -> method -> _flatten_children -> visit -> warn)
	"""
	flat: list[Element] = []
	seen_keys: set[str] = set()

	def visit(item: Child) -> None:
		if isinstance(item, Iterable) and not isinstance(item, str):
			# If any Node/ComponentNode yielded by this iterable lacks a key,
			# emit a single warning for this iterable (dev mode only).
			missing_key = False
			for sub in item:
				if isinstance(sub, (Node, ComponentNode)) and sub.key is None:
					missing_key = True
				visit(sub)
			if missing_key:
				# Warn once per iterable without keys on its elements.
				clean_name = clean_element_name(parent_name)
				warnings.warn(
					(
						f"[Pulse] Iterable children of {clean_name} contain elements without 'key'. "
						"Add a stable 'key' to each element inside iterables to improve reconciliation."
					),
					stacklevel=warn_stacklevel,
				)
		else:
			# Not an iterable child: must be a Element or primitive. Check for
			# duplicate keys on nodes.
			if isinstance(item, (Node, ComponentNode)) and item.key is not None:
				if item.key in seen_keys:
					clean_name = clean_element_name(parent_name)
					raise ValueError(
						f"[Pulse] Duplicate key '{item.key}' found among children of {clean_name}. "
						+ "Keys must be unique per sibling set."
					)
				seen_keys.add(item.key)
			flat.append(item)

	for child in children:
		visit(child)

	return flat


def _takes_children(fn: Callable[..., Any]) -> bool:
	"""Return True if function accepts children via `*children` parameter.

	Convention: A component accepts children if and only if it has a VAR_POSITIONAL
	parameter named "children". This convention should be documented in user-facing docs.
	"""
	try:
		sig = signature(fn)
	except (ValueError, TypeError):
		# Builtins or callables without inspectable signature: assume no children
		return False
	for p in sig.parameters.values():
		if p.kind is Parameter.VAR_POSITIONAL and p.name == "children":
			return True
	return False


# ----------------------------------------------------------------------------
# Formatting helpers (internal)
# ----------------------------------------------------------------------------


def clean_element_name(parent_name: str) -> str:
	"""Strip $$ prefix and hexadecimal suffix from ReactComponent tags in warning messages.

	ReactComponent tags are in the format <$$ComponentName_1a2b> or <$$ComponentName_1a2b.prop>.
	This function strips the $$ prefix and _1a2b suffix to show just the component name.
	"""

	# Match ReactComponent tags: <$$ComponentName_hex> or <$$ComponentName_hex.prop>
	# Strip the $$ prefix and _hex suffix but keep the rest (hex digits are 0-9, a-f)
	return re.sub(r"\$\$([^_]+)_[0-9a-f]+", r"\1", parent_name)


def _infer_component_name(fn: Callable[..., Any]) -> str:
	# Unwrap partials and single-level wrappers
	original = fn
	if isinstance(original, functools.partial):
		original = original.func  # type: ignore[attr-defined]

	name: str | None = getattr(original, "__name__", None)
	if name and name != "<lambda>":
		return name

	qualname: str | None = getattr(original, "__qualname__", None)
	if qualname and "<locals>" not in qualname:
		# Best-effort: take the last path component
		return qualname.split(".")[-1]

	# Callable instances (classes defining __call__)
	cls = getattr(original, "__class__", None)
	if cls and getattr(cls, "__name__", None):
		return cls.__name__

	# Fallback
	return "Component"


def _callable_qualname(fn: Callable[..., Any]) -> str:
	mod = getattr(fn, "__module__", None) or "__main__"
	qual = (
		getattr(fn, "__qualname__", None)
		or getattr(fn, "__name__", None)
		or "<callable>"
	)
	return f"{mod}.{qual}"


def _pretty_repr(node: Element):
	if isinstance(node, Node):
		return f"<{node.tag}>"
	if isinstance(node, ComponentNode):
		return f"<{node.name}"
	return repr(node)


def _short_args(args: tuple[Any, ...], max_items: int = 4) -> list[str] | str:
	if not args:
		return []
	out: list[str] = []
	for a in args[: max_items - 1]:
		s = repr(a)
		if len(s) > 32:
			s = s[:29] + "…" + s[-1]
		out.append(s)
	if len(args) > (max_items - 1):
		out.append(f"…(+{len(args) - (max_items - 1)})")
	return out


def _short_props(
	props: dict[str, Any] | None, max_items: int = 6
) -> dict[str, Any] | str:
	if not props:
		return {}
	items = list(props.items())
	if len(items) <= max_items:
		return props
	head = dict(items[: max_items - 1])
	return {**head, "…": f"+{len(items) - (max_items - 1)} more"}


def _short_children(
	children: Sequence[Child] | None, max_items: int = 4
) -> list[str] | str:
	if not children:
		return []
	out: list[str] = []
	i = 0
	while i < len(children) and len(out) < max_items:
		child = children[i]
		i += 1
		if isinstance(child, Iterable) and not isinstance(child, str):
			child = list(child)
			n_items = min(len(child), max_items - len(out))
			out.extend(_pretty_repr(c) for c in child[:n_items])
		else:
			out.append(_pretty_repr(child))
	if len(children) > (max_items - 1):
		out.append(f"…(+{len(children) - (max_items - 1)})")
	return out
