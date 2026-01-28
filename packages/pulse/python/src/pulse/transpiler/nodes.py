from __future__ import annotations

import ast
import datetime as dt
import string
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from inspect import currentframe, isfunction, signature
from typing import (
	TYPE_CHECKING,
	Any,
	Generic,
	Protocol,
	TypeAlias,
	TypeVar,
	cast,
	overload,
	override,
)
from typing import Literal as Lit

from pulse.env import env
from pulse.transpiler.errors import TranspileError
from pulse.transpiler.vdom import VDOMExpr, VDOMNode, VDOMPrimitive

if TYPE_CHECKING:
	from pulse.transpiler.transpiler import Transpiler

_T = TypeVar("_T")
Primitive: TypeAlias = bool | int | float | str | dt.datetime | None

_JS_IDENTIFIER_START = set(string.ascii_letters + "_")
_JS_IDENTIFIER_CONTINUE = set(string.ascii_letters + string.digits + "_")


def to_js_identifier(name: str) -> str:
	"""Normalize a string to a JS-compatible identifier."""
	if not name:
		return "_"
	out: list[str] = []
	for ch in name:
		out.append(ch if ch in _JS_IDENTIFIER_CONTINUE else "_")
	if not out or out[0] not in _JS_IDENTIFIER_START:
		out.insert(0, "_")
	return "".join(out)


# =============================================================================
# Global registries
# =============================================================================

# Global registry: id(value) -> Expr
# Used by Expr.of() to resolve registered Python values
EXPR_REGISTRY: dict[int, "Expr"] = {}


# =============================================================================
# Base classes
# =============================================================================
class Expr(ABC):
	"""Base class for expression nodes.

	Provides hooks for custom transpilation behavior:
	- transpile_call: customize behavior when called as a function
	- transpile_getattr: customize attribute access
	- transpile_subscript: customize subscript access

	And serialization for client-side rendering:
	- render: serialize to dict for client renderer (stub for now)
	"""

	__slots__: tuple[str, ...] = ()

	@abstractmethod
	def emit(self, out: list[str]) -> None:
		"""Emit this expression as JavaScript/JSX code into the output buffer."""

	def precedence(self) -> int:
		"""Operator precedence (higher = binds tighter). Default: primary (20)."""
		return 20

	# -------------------------------------------------------------------------
	# Transpilation hooks (override to customize behavior)
	# -------------------------------------------------------------------------

	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		"""Called when this expression is used as a function: expr(args).

		Override to customize call behavior.
		Default emits a Call expression with args transpiled.

		Args and keywords are raw Python AST nodes (not yet transpiled).
		Use ctx.emit_expr() to convert them to Expr as needed.
		Keywords with kw.arg=None are **spread syntax.
		"""
		if keywords:
			has_spread = any(kw.arg is None for kw in keywords)
			if has_spread:
				raise TranspileError("Spread (**expr) not supported in this call")
			raise TranspileError("Keyword arguments not supported in call")
		return Call(self, [ctx.emit_expr(a) for a in args])

	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		"""Called when an attribute is accessed: expr.attr.

		Override to customize attribute access.
		Default returns Member(self, attr).
		"""
		return Member(self, attr)

	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		"""Called when subscripted: expr[key].

		Override to customize subscript behavior.
		Default returns Subscript(self, emitted_key).
		"""
		if isinstance(key, ast.Tuple):
			raise TranspileError(
				"Multiple indices not supported in subscript", node=key
			)
		return Subscript(self, ctx.emit_expr(key))

	# -------------------------------------------------------------------------
	# Serialization for client-side rendering
	# -------------------------------------------------------------------------

	@abstractmethod
	def render(self) -> VDOMPrimitive | VDOMExpr:
		"""Serialize this expression node for client-side rendering.

		Returns a VDOMNode (primitive or dict) that can be JSON-serialized and
		evaluated on the client. Override in each concrete Expr subclass.

		Raises TypeError for nodes that cannot be serialized (e.g., Transformer).
		"""

	# -------------------------------------------------------------------------
	# Python dunder methods for natural syntax in @javascript functions
	# These return Expr nodes that represent the operations at transpile time.
	# -------------------------------------------------------------------------

	def __call__(self, *args: object, **kwargs: object) -> "Call":
		"""Allow calling Expr objects in Python code.

		Returns a Call expression. Subclasses may override to return more
		specific types (e.g., Element for JSX components).
		"""
		return Call(self, [Expr.of(a) for a in args])

	def __getitem__(self, key: object) -> "Subscript":
		"""Allow subscript access on Expr objects in Python code.

		Returns a Subscript expression for type checking.
		"""
		return Subscript(self, Expr.of(key))

	def __getattr__(self, attr: str) -> "Member":
		"""Allow attribute access on Expr objects in Python code.

		Returns a Member expression for type checking.
		"""
		return Member(self, attr)

	def __add__(self, other: object) -> "Binary":
		"""Allow + operator on Expr objects."""
		return Binary(self, "+", Expr.of(other))

	def __sub__(self, other: object) -> "Binary":
		"""Allow - operator on Expr objects."""
		return Binary(self, "-", Expr.of(other))

	def __mul__(self, other: object) -> "Binary":
		"""Allow * operator on Expr objects."""
		return Binary(self, "*", Expr.of(other))

	def __truediv__(self, other: object) -> "Binary":
		"""Allow / operator on Expr objects."""
		return Binary(self, "/", Expr.of(other))

	def __mod__(self, other: object) -> "Binary":
		"""Allow % operator on Expr objects."""
		return Binary(self, "%", Expr.of(other))

	def __and__(self, other: object) -> "Binary":
		"""Allow & operator on Expr objects (maps to &&)."""
		return Binary(self, "&&", Expr.of(other))

	def __or__(self, other: object) -> "Binary":
		"""Allow | operator on Expr objects (maps to ||)."""
		return Binary(self, "||", Expr.of(other))

	def __neg__(self) -> "Unary":
		"""Allow unary - operator on Expr objects."""
		return Unary("-", self)

	def __pos__(self) -> "Unary":
		"""Allow unary + operator on Expr objects."""
		return Unary("+", self)

	def __invert__(self) -> "Unary":
		"""Allow ~ operator on Expr objects (maps to !)."""
		return Unary("!", self)

	# -------------------------------------------------------------------------
	# Type casting and wrapper methods
	# -------------------------------------------------------------------------

	def as_(self, typ_: "_T | type[_T]") -> "_T":
		"""Cast this expression to a type or use as a decorator.

		Usage as decorator:
			@Import(...).as_
			def fn(): ...

		Usage for type casting:
			clsx = Import(...).as_(Callable[[str, ...], str])

		If typ_ is a user-defined callable (function or lambda),
		wraps the expression in a Signature node that stores the callable's
		signature for type introspection.
		"""
		# Only wrap for user-defined functions (lambdas, def functions)
		# Skip for types (str, int, etc.) used as type annotations
		if isfunction(typ_):
			try:
				sig = signature(typ_)
				return cast("_T", Signature(self, sig))
			except (ValueError, TypeError):
				# Signature not available (e.g., for built-ins), return self
				pass

		return cast("_T", self)

	def jsx(self) -> "Jsx":
		"""Wrap this expression as a JSX component.

		When called in transpiled code, produces Element(tag=self, ...).
		"""
		return Jsx(self)

	# -------------------------------------------------------------------------
	# Registry for Python value -> Expr mapping
	# -------------------------------------------------------------------------

	@staticmethod
	def of(value: Any) -> Expr:
		"""Convert a Python value to an Expr.

		Resolution order:
		1. Already an Expr: returned as-is
		2. Registered in EXPR_REGISTRY: return the registered expr
		3. Primitives: str/int/float -> Literal, bool -> Literal, None -> Literal(None)
		4. Collections: list/tuple -> Array, dict -> Object (recursively converted)
		5. set -> Call(Identifier("Set"), [Array(...)])

		Raises TypeError for unconvertible values.
		"""
		# Already an Expr
		if isinstance(value, Expr):
			return value

		# Check registry (for modules, functions, etc.)
		if (expr := EXPR_REGISTRY.get(id(value))) is not None:
			return expr

		# Primitives - must check bool before int since bool is subclass of int
		if isinstance(value, bool):
			return Literal(value)
		if isinstance(value, (int, float, str)):
			return Literal(value)
		if value is None:
			return Literal(None)

		# Collections
		if isinstance(value, (list, tuple)):
			return Array([Expr.of(v) for v in value])
		if isinstance(value, dict):
			props = [(str(k), Expr.of(v)) for k, v in value.items()]  # pyright: ignore[reportUnknownArgumentType]
			return Object(props)
		if isinstance(value, set):
			# new Set([...])
			return New(Identifier("Set"), [Array([Expr.of(v) for v in value])])

		raise TypeError(f"Cannot convert {type(value).__name__} to Expr")

	@staticmethod
	def register(value: Any, expr: Expr | Callable[..., Expr]) -> None:
		"""Register a Python value for conversion via Expr.of().

		Args:
			value: The Python object to register (function, constant, etc.)
			expr: Either an Expr or a Callable[..., Expr] (will be wrapped in Transformer)
		"""
		if callable(expr) and not isinstance(expr, Expr):
			expr = Transformer(expr)
		EXPR_REGISTRY[id(value)] = expr


class Stmt(ABC):
	"""Base class for statement nodes."""

	__slots__: tuple[str, ...] = ()

	@abstractmethod
	def emit(self, out: list[str]) -> None:
		"""Emit this statement as JavaScript code into the output buffer."""


# =============================================================================
# Data Nodes
# =============================================================================


class ExprWrapper(Expr):
	"""Base class for Expr wrappers that delegate to an underlying expression.

	Subclasses must define an `expr` attribute (via __slots__ or dataclass).
	All Expr methods delegate to self.expr by default. Override specific
	methods to customize behavior.
	"""

	__slots__: tuple[str, ...] = ("expr",)
	expr: Expr

	@override
	def emit(self, out: list[str]) -> None:
		self.expr.emit(out)

	@override
	def render(self) -> VDOMPrimitive | VDOMExpr:
		return self.expr.render()

	@override
	def precedence(self) -> int:
		return self.expr.precedence()

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		return self.expr.transpile_call(args, keywords, ctx)

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		return self.expr.transpile_getattr(attr, ctx)

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		return self.expr.transpile_subscript(key, ctx)

	@override
	def __call__(self, *args: object, **kwargs: object) -> Expr:  # pyright: ignore[reportIncompatibleMethodOverride]
		return self.expr(*args, **kwargs)

	@override
	def __getitem__(self, key: object) -> Expr:  # pyright: ignore[reportIncompatibleMethodOverride]
		return self.expr[key]

	@override
	def __getattr__(self, attr: str) -> Expr:  # pyright: ignore[reportIncompatibleMethodOverride]
		return getattr(self.expr, attr)


@dataclass(slots=True, init=False)
class Jsx(ExprWrapper):
	"""JSX wrapper that makes any Expr callable as a component.

	When called in transpiled code, produces Element(tag=expr, ...).
	This enables patterns like `Jsx(Member(AppShell, "Header"))` to emit
	`<AppShell.Header ... />`.

	Example:
		app_shell = Import("AppShell", "@mantine/core")
		Header = Jsx(Member(app_shell, "Header"))
		# In @javascript:
		# Header(height=60) -> <AppShell_1.Header height={60} />
	"""

	expr: Expr
	id: str

	def __init__(self, expr: Expr) -> None:
		from pulse.transpiler.id import next_id

		self.expr = expr
		self.id = next_id()

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: "Transpiler",
	) -> Expr:
		"""Transpile a call to this JSX wrapper into an Element.

		Positional args become children, keyword args become props.
		The `key` kwarg is extracted specially. Spread (**expr) is supported.
		"""
		children: list[Node] = [ctx.emit_expr(a) for a in args]

		props: list[tuple[str, Prop] | Spread] = []
		key: str | Expr | None = None
		for kw in keywords:
			if kw.arg is None:
				# **spread syntax
				props.append(spread_dict(ctx.emit_expr(kw.value)))
			else:
				k = kw.arg
				v = ctx.emit_expr(kw.value)
				if k == "key":
					# Accept any expression as key for transpilation
					if isinstance(v, Literal) and isinstance(v.value, str):
						key = v.value  # Optimize string literals
					else:
						key = v  # Keep as expression
				else:
					props.append((k, v))

		return Element(
			tag=self.expr,
			props=props if props else None,
			children=children if children else None,
			key=key,
		)

	@override
	def __call__(self, *args: Any, **kwargs: Any) -> Element:
		"""Allow calling Jsx in Python code.

		Supports two usage patterns:
		1. Decorator: @Jsx(expr) def Component(...): ...
		2. Call: Jsx(expr)(props, children) -> Element
		"""

		# Normal call: build Element
		props: dict[str, Any] = {}
		key: str | None = None
		children: list[Node] = list(args)

		for k, v in kwargs.items():
			if k == "key":
				if v is None:
					continue
				if not isinstance(v, str):
					raise ValueError("key must be a string")
				key = v
			else:
				props[k] = v

		return Element(
			tag=self.expr,
			props=props if props else None,
			children=children if children else None,
			key=key,
		)


@dataclass(slots=True)
class Signature(ExprWrapper):
	"""Wraps an Expr with signature information for type checking.

	When you call expr.as_(callable_type), this creates a Signature wrapper
	that stores the callable's signature for introspection, while delegating
	all other behavior to the wrapped expression.

	Example:
		button = Import("Button", "@mantine/core")
		typed_button = Signature(button, signature_of_callable)
	"""

	expr: Expr
	sig: Any  # inspect.Signature, but use Any for type compatibility


@dataclass(slots=True)
class Value(Expr):
	"""Wraps a non-primitive Python value for pass-through serialization.

	Use cases:
	- Complex prop values: options={"a": 1, "b": 2}
	- Server-computed data passed to client components
	- Any value that doesn't need expression semantics
	"""

	value: Any

	@override
	def emit(self, out: list[str]) -> None:
		_emit_value(self.value, out)

	@override
	def render(self) -> VDOMExpr:
		raise TypeError(
			"Value cannot be rendered as VDOMExpr; unwrap with .value instead"
		)


class Element(Expr):
	"""A React element: built-in tag, fragment, or client component.

	Tag conventions:
	- "" (empty string): Fragment
	- "div", "span", etc.: HTML element
	- "$$ComponentId": Client component (registered in JS registry)
	- Expr (Import, Member, etc.): Direct component reference for transpilation

	Props can be either:
	- tuple[str, Prop]: key-value pair
	- Spread: spread expression (...expr)
	"""

	__slots__: tuple[str, ...] = ("tag", "props", "children", "key")

	tag: str | Expr
	props: Sequence[tuple[str, Prop] | Spread] | dict[str, Any] | None
	children: Sequence[Node] | None
	key: str | Expr | None

	def __init__(
		self,
		tag: str | Expr,
		props: Sequence[tuple[str, Prop] | Spread] | dict[str, Any] | None = None,
		children: Sequence[Node] | None = None,
		key: str | Expr | None = None,
	) -> None:
		self.tag = tag
		self.props = props
		if children is None:
			self.children = None
		else:
			if isinstance(tag, str):
				parent_name: str | Expr = tag[2:] if tag.startswith("$$") else tag
			else:
				parent_name = tag
			self.children = flatten_children(
				children,
				parent_name=parent_name,
				warn_stacklevel=None,
			)
		self.key = key

	def _emit_key(self, out: list[str]) -> None:
		"""Emit key prop (string or expression)."""
		if self.key is None:
			return
		if isinstance(self.key, str):
			out.append('key="')
			out.append(_escape_jsx_attr(self.key))
			out.append('"')
		else:
			# Expression key: key={expr}
			out.append("key={")
			self.key.emit(out)
			out.append("}")

	@override
	def emit(self, out: list[str]) -> None:
		# Fragment (only for string tags)
		if self.tag == "":
			if self.key is not None:
				# Fragment with key needs explicit Fragment component
				out.append("<Fragment ")
				self._emit_key(out)
				out.append(">")
				for c in self.children or []:
					_emit_jsx_child(c, out)
				out.append("</Fragment>")
			else:
				out.append("<>")
				for c in self.children or []:
					_emit_jsx_child(c, out)
				out.append("</>")
			return

		# Resolve tag - either emit Expr or use string (strip $$ prefix)
		tag_out: list[str] = []
		if isinstance(self.tag, Expr):
			self.tag.emit(tag_out)
		else:
			tag_out.append(self.tag[2:] if self.tag.startswith("$$") else self.tag)
		tag_str = "".join(tag_out)

		# Build props into a separate buffer to check if empty
		props_out: list[str] = []
		if self.key is not None:
			self._emit_key(props_out)
		if self.props:
			# Handle both dict (from render path) and sequence (from transpilation)
			# Dict case: items() yields tuple[str, Any], never Spread
			# Sequence case: already list[tuple[str, Prop] | Spread]
			props_iter: Iterable[tuple[str, Any]] | Sequence[tuple[str, Prop] | Spread]
			if isinstance(self.props, dict):
				props_iter = self.props.items()
			else:
				props_iter = self.props
			for prop in props_iter:
				if props_out:
					props_out.append(" ")
				if isinstance(prop, Spread):
					props_out.append("{...")
					prop.expr.emit(props_out)
					props_out.append("}")
				else:
					name, value = prop
					_emit_jsx_prop(name, value, props_out)

		# Build children into a separate buffer to check if empty
		children_out: list[str] = []
		for c in self.children or []:
			_emit_jsx_child(c, children_out)

		# Self-closing if no children
		if not children_out:
			out.append("<")
			out.append(tag_str)
			if props_out:
				out.append(" ")
				out.extend(props_out)
			out.append(" />")
			return

		# Open tag
		out.append("<")
		out.append(tag_str)
		if props_out:
			out.append(" ")
			out.extend(props_out)
		out.append(">")
		# Children
		out.extend(children_out)
		# Close tag
		out.append("</")
		out.append(tag_str)
		out.append(">")

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		"""Transpile subscript as adding children to this element.

		Handles both single children and tuple of children.
		"""
		if self.children:
			raise TranspileError(
				f"Element '{self.tag}' already has children; cannot add more via subscript"
			)

		# Convert key to list of children
		if isinstance(key, ast.Tuple):
			children = [ctx.emit_expr(e) for e in key.elts]
		else:
			children = [ctx.emit_expr(key)]

		return Element(
			tag=self.tag,
			props=self.props,
			children=children,
			key=self.key,
		)

	@override
	def __getitem__(self, key: Any) -> Element:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Return new Element with children set via subscript.

		Raises if this element already has children.
		Accepts a single child or a Sequence of children.
		"""
		if self.children:
			raise ValueError(
				f"Element '{self.tag}' already has children; cannot add more via subscript"
			)

		# Convert key to sequence of children
		if isinstance(key, (list, tuple)):
			children = list(cast(list[Any] | tuple[Any, ...], key))
		else:
			children = [key]

		return Element(
			tag=self.tag,
			props=self.props,
			children=children,
			key=self.key,
		)

	def with_children(self, children: Sequence[Node]) -> Element:
		"""Return new Element with children set.

		Raises if this element already has children.
		"""
		if self.children:
			raise ValueError(
				f"Element '{self.tag}' already has children; cannot add more via subscript"
			)
		return Element(
			tag=self.tag,
			props=self.props,
			children=list(children),
			key=self.key,
		)

	def props_dict(self) -> dict[str, Any]:
		"""Convert props to dict for rendering.

		Raises TypeError if props contain Spread (only valid in transpilation).
		"""
		if not self.props:
			return {}
		# Already a dict (from renderer reconciliation)
		if isinstance(self.props, dict):
			return self.props
		# Sequence of (key, value) pairs or Spread
		result: dict[str, Any] = {}
		for prop in self.props:
			if isinstance(prop, Spread):
				raise TypeError(
					"Element with spread props cannot be rendered; spread is only valid during transpilation"
				)
			k, v = prop
			result[k] = v
		return result

	@override
	def render(self):
		"""Element rendering is handled by Renderer.render_node(), not render().

		This method validates render-time constraints and raises TypeError
		because Element produces VDOMElement, not VDOMExpr.
		"""
		# Validate key is string or numeric (not arbitrary Expr) during rendering
		if self.key is not None and not isinstance(self.key, (str, int)):
			raise TypeError(
				f"Element key must be a string or int for rendering, got {type(self.key).__name__}. "
				+ "Expression keys are only valid during transpilation (emit)."
			)
		raise TypeError(
			"Element cannot be rendered as VDOMExpr; use Renderer.render_node() instead"
		)


@dataclass(slots=True)
class PulseNode:
	"""A Pulse server-side component instance.

	During rendering, PulseNode is called and replaced by its returned tree.
	Can only appear in VDOM context (render path), never in transpiled code.
	"""

	fn: Any  # Callable[..., Node]
	args: tuple[Any, ...] = ()
	kwargs: dict[str, Any] = field(default_factory=dict)
	key: str | None = None
	name: str | None = None  # Optional component name for debug messages.
	# Renderer state (mutable, set during render)
	hooks: Any = None  # HookContext
	contents: Node | None = None

	def emit(self, out: list[str]) -> None:
		fn_name = getattr(self.fn, "__name__", "unknown")
		raise TypeError(
			f"Cannot transpile PulseNode '{fn_name}'. "
			+ "Server components must be rendered, not transpiled."
		)

	def __getitem__(self, children_arg: "Node | tuple[Node, ...]"):
		if self.args:
			raise ValueError(
				"PulseNode already received positional args; pass children in the call or via brackets, not both."
			)
		if not isinstance(children_arg, tuple):
			children_arg = (children_arg,)
		parent_name = self.name
		if parent_name is None:
			parent_name = getattr(self.fn, "__name__", "Component")
		flat = flatten_children(
			children_arg,
			parent_name=parent_name,
			warn_stacklevel=None,
		)
		return PulseNode(
			fn=self.fn,
			args=tuple(flat),
			kwargs=self.kwargs,
			key=self.key,
			name=self.name,
		)


# =============================================================================
# Children normalization helpers
# =============================================================================
def flatten_children(
	children: Sequence[Node | Iterable[Node]],
	*,
	parent_name: str | Expr,
	warn_stacklevel: int | None = None,
) -> list[Node]:
	if env.pulse_env == "dev":
		return _flatten_children_dev(
			children, parent_name=parent_name, warn_stacklevel=warn_stacklevel
		)
	return _flatten_children_prod(children)


def _flatten_children_prod(children: Sequence[Node | Iterable[Node]]) -> list[Node]:
	flat: list[Node] = []

	def visit(item: Node | Iterable[Node]) -> None:
		if isinstance(item, dict):
			raise TypeError("Dict is not a valid child")
		if isinstance(item, Iterable) and not isinstance(item, str):
			for sub in item:
				visit(sub)
		else:
			flat.append(item)

	for child in children:
		visit(child)

	return flat


def _flatten_children_dev(
	children: Sequence[Node | Iterable[Node]],
	*,
	parent_name: str | Expr,
	warn_stacklevel: int | None = None,
) -> list[Node]:
	flat: list[Node] = []
	seen_keys: set[str] = set()

	def visit(item: Node | Iterable[Node]) -> None:
		nonlocal warn_stacklevel
		if isinstance(item, dict):
			raise TypeError("Dict is not a valid child")
		if isinstance(item, Iterable) and not isinstance(item, str):
			missing_key = False
			for sub in item:
				if isinstance(sub, PulseNode) and sub.key is None:
					missing_key = True
				if isinstance(sub, Element) and _normalize_key(sub.key) is None:
					missing_key = True
				visit(sub)  # type: ignore[arg-type]
			if missing_key:
				if warn_stacklevel is None:
					stacklevel = 1
					frame = currentframe()
					if frame is not None:
						frame = frame.f_back
						internal_prefixes = (
							"pulse",
							"pulse_mantine",
							"pulse_ag_grid",
							"pulse_recharts",
							"pulse_lucide",
							"pulse_msal",
							"pulse_aws",
						)
						while frame is not None:
							module = frame.f_globals.get("__name__", "")
							if module and not any(
								module == prefix or module.startswith(f"{prefix}.")
								for prefix in internal_prefixes
							):
								break
							stacklevel += 1
							frame = frame.f_back
						if frame is not None:
							stacklevel += 1
					warn_stacklevel = stacklevel
				clean_name = clean_element_name(parent_name)
				warnings.warn(
					(
						f"[Pulse] Iterable children of {clean_name} contain elements without 'key'. "
						"Add a stable 'key' to each element inside iterables to improve reconciliation."
					),
					stacklevel=warn_stacklevel,
				)
		else:
			if isinstance(item, PulseNode) and item.key is not None:
				if item.key in seen_keys:
					clean_name = clean_element_name(parent_name)
					raise ValueError(
						f"[Pulse] Duplicate key '{item.key}' found among children of {clean_name}. "
						+ "Keys must be unique per sibling set."
					)
				seen_keys.add(item.key)
			if isinstance(item, Element):
				key = _normalize_key(item.key)
				if key is not None:
					if key in seen_keys:
						clean_name = clean_element_name(parent_name)
						raise ValueError(
							f"[Pulse] Duplicate key '{key}' found among children of {clean_name}. "
							+ "Keys must be unique per sibling set."
						)
					seen_keys.add(key)
			flat.append(item)

	for child in children:
		visit(child)

	return flat


def clean_element_name(parent_name: str | Expr) -> str:
	def expr_name(expr: Expr) -> str:
		while isinstance(expr, ExprWrapper):
			expr = expr.expr
		if isinstance(expr, Member):
			base = expr_name(expr.obj)
			return f"{base}.{expr.prop}" if base else expr.prop
		if isinstance(expr, Identifier):
			return expr.name
		if expr.__class__.__name__ == "Import":
			name = getattr(expr, "name", None)
			if isinstance(name, str) and name:
				return name
		out: list[str] = []
		expr.emit(out)
		return "".join(out)

	if isinstance(parent_name, Expr):
		parent_name = expr_name(parent_name)
	if parent_name.startswith("<") and parent_name.endswith(">"):
		return parent_name
	return f"<{parent_name}>"


def _normalize_key(key: object | None) -> str | None:
	if isinstance(key, Literal):
		return key.value if isinstance(key.value, str) else None
	return key if isinstance(key, str) else None


# =============================================================================
# Expression Nodes
# =============================================================================


@dataclass(slots=True)
class Identifier(Expr):
	"""JS identifier: x, foo, myFunc"""

	name: str

	@override
	def emit(self, out: list[str]) -> None:
		out.append(self.name)

	@override
	def render(self) -> VDOMExpr:
		return {"t": "id", "name": self.name}


@dataclass(slots=True)
class Literal(Expr):
	"""JS literal: 42, "hello", true, null"""

	value: int | float | str | bool | None

	@override
	def emit(self, out: list[str]) -> None:
		if self.value is None:
			out.append("null")
		elif isinstance(self.value, bool):
			out.append("true" if self.value else "false")
		elif isinstance(self.value, str):
			out.append('"')
			out.append(_escape_string(self.value))
			out.append('"')
		else:
			out.append(str(self.value))

	@override
	def render(self) -> VDOMPrimitive:
		return self.value


class Undefined(Expr):
	"""JS undefined literal.

	Use Undefined() for JS `undefined`. Literal(None) emits `null`.
	This is a singleton-like class with no fields.
	"""

	__slots__: tuple[str, ...] = ()

	@override
	def emit(self, out: list[str]) -> None:
		out.append("undefined")

	@override
	def render(self) -> VDOMExpr:
		return {"t": "undef"}


# Singleton instance for convenience
UNDEFINED = Undefined()


@dataclass(slots=True)
class Array(Expr):
	"""JS array: [a, b, c]"""

	elements: Sequence[Expr]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("[")
		for i, e in enumerate(self.elements):
			if i > 0:
				out.append(", ")
			e.emit(out)
		out.append("]")

	@override
	def render(self) -> VDOMExpr:
		return {"t": "array", "items": [e.render() for e in self.elements]}


@dataclass(slots=True)
class Object(Expr):
	"""JS object: { key: value, ...spread }

	Props can be either:
	- tuple[str, Expr]: key-value pair
	- Spread: spread expression (...expr)
	"""

	props: Sequence[tuple[str, Expr] | Spread]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("{")
		for i, prop in enumerate(self.props):
			if i > 0:
				out.append(", ")
			if isinstance(prop, Spread):
				prop.emit(out)
			else:
				k, v = prop
				out.append('"')
				out.append(_escape_string(k))
				out.append('": ')
				v.emit(out)
		out.append("}")

	@override
	def render(self) -> VDOMExpr:
		rendered_props: dict[str, VDOMNode] = {}
		for prop in self.props:
			if isinstance(prop, Spread):
				raise TypeError("Object spread cannot be rendered to VDOM")
			k, v = prop
			rendered_props[k] = v.render()
		return {"t": "object", "props": rendered_props}


@dataclass(slots=True)
class Member(Expr):
	"""JS member access: obj.prop"""

	obj: Expr
	prop: str

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.obj, out)
		out.append(".")
		out.append(self.prop)

	@override
	def render(self) -> VDOMExpr:
		return {"t": "member", "obj": self.obj.render(), "prop": self.prop}


@dataclass(slots=True)
class Subscript(Expr):
	"""JS subscript access: obj[key]"""

	obj: Expr
	key: Expr

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.obj, out)
		out.append("[")
		self.key.emit(out)
		out.append("]")

	@override
	def render(self) -> VDOMExpr:
		return {"t": "sub", "obj": self.obj.render(), "key": self.key.render()}


@dataclass(slots=True)
class Call(Expr):
	"""JS function call: fn(args)"""

	callee: Expr
	args: Sequence[Expr]

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.callee, out)
		out.append("(")
		for i, a in enumerate(self.args):
			if i > 0:
				out.append(", ")
			a.emit(out)
		out.append(")")

	@override
	def render(self) -> VDOMExpr:
		return {
			"t": "call",
			"callee": self.callee.render(),
			"args": [a.render() for a in self.args],
		}


@dataclass(slots=True)
class Unary(Expr):
	"""JS unary expression: -x, !x, typeof x"""

	op: str
	operand: Expr

	@override
	def precedence(self) -> int:
		op = self.op
		tag = "+u" if op == "+" else ("-u" if op == "-" else op)
		return _PRECEDENCE.get(tag, 17)

	@override
	def emit(self, out: list[str]) -> None:
		if self.op in {"typeof", "await", "void", "delete"}:
			out.append(self.op)
			out.append(" ")
		else:
			out.append(self.op)
		if (
			self.op in {"+", "-"}
			and isinstance(self.operand, Unary)
			and self.operand.op == self.op
		):
			out.append("(")
			self.operand.emit(out)
			out.append(")")
			return
		_emit_paren(self.operand, self.op, "unary", out)

	@override
	def render(self) -> VDOMExpr:
		if self.op == "await":
			raise TypeError("await is not supported in VDOM expressions")
		return {"t": "unary", "op": self.op, "arg": self.operand.render()}


@dataclass(slots=True)
class Binary(Expr):
	"""JS binary expression: x + y, a && b"""

	left: Expr
	op: str
	right: Expr

	@override
	def precedence(self) -> int:
		return _PRECEDENCE.get(self.op, 0)

	@override
	def emit(self, out: list[str]) -> None:
		# Special: ** with unary +/- on left needs parens
		force_left = (
			self.op == "**"
			and isinstance(self.left, Unary)
			and self.left.op in {"-", "+"}
		)
		if force_left:
			out.append("(")
			self.left.emit(out)
			out.append(")")
		else:
			_emit_paren(self.left, self.op, "left", out)
		out.append(" ")
		out.append(self.op)
		out.append(" ")
		_emit_paren(self.right, self.op, "right", out)

	@override
	def render(self) -> VDOMExpr:
		return {
			"t": "binary",
			"op": self.op,
			"left": self.left.render(),
			"right": self.right.render(),
		}


@dataclass(slots=True)
class Ternary(Expr):
	"""JS ternary expression: cond ? a : b"""

	cond: Expr
	then: Expr
	else_: Expr

	@override
	def precedence(self) -> int:
		return _PRECEDENCE["?:"]

	@override
	def emit(self, out: list[str]) -> None:
		self.cond.emit(out)
		out.append(" ? ")
		self.then.emit(out)
		out.append(" : ")
		self.else_.emit(out)

	@override
	def render(self) -> VDOMExpr:
		return {
			"t": "ternary",
			"cond": self.cond.render(),
			"then": self.then.render(),
			"else_": self.else_.render(),
		}


@dataclass(slots=True)
class Arrow(Expr):
	"""JS arrow function: (x) => expr or (x) => { ... }

	body can be:
	- Expr: expression body, emits as `() => expr`
	- Sequence[Stmt]: statement body, emits as `() => { stmt1; stmt2; }`
	"""

	params: Sequence[str]
	body: Expr | Sequence[Stmt]

	@override
	def precedence(self) -> int:
		# Arrow functions have very low precedence (assignment level)
		# This ensures they get wrapped in parens when used as callee in Call
		return 3

	@override
	def emit(self, out: list[str]) -> None:
		if len(self.params) == 1:
			out.append(self.params[0])
		else:
			out.append("(")
			out.append(", ".join(self.params))
			out.append(")")
		out.append(" => ")
		if isinstance(self.body, Expr):
			self.body.emit(out)
		else:
			out.append("{ ")
			for stmt in self.body:
				stmt.emit(out)
				out.append(" ")
			out.append("}")

	@override
	def render(self) -> VDOMExpr:
		if not isinstance(self.body, Expr):
			raise TypeError("Arrow with statement body cannot be rendered as VDOMExpr")
		return {"t": "arrow", "params": list(self.params), "body": self.body.render()}


@dataclass(slots=True)
class Template(Expr):
	"""JS template literal: `hello ${name}`

	Parts alternate: [str, Expr, str, Expr, str, ...]
	Always starts and ends with a string (may be empty).
	"""

	parts: Sequence[str | Expr]  # alternating, starting with str

	@override
	def emit(self, out: list[str]) -> None:
		out.append("`")
		for p in self.parts:
			if isinstance(p, str):
				out.append(_escape_template(p))
			else:
				out.append("${")
				p.emit(out)
				out.append("}")
		out.append("`")

	@override
	def render(self) -> VDOMExpr:
		rendered_parts: list[str | VDOMNode] = []
		for p in self.parts:
			if isinstance(p, str):
				rendered_parts.append(p)
			else:
				rendered_parts.append(p.render())
		return {"t": "template", "parts": rendered_parts}


@dataclass(slots=True)
class Spread(Expr):
	"""JS spread: ...expr"""

	expr: Expr

	@override
	def emit(self, out: list[str]) -> None:
		out.append("...")
		self.expr.emit(out)

	@override
	def render(self) -> VDOMExpr:
		raise TypeError("Spread cannot be rendered as VDOMExpr directly")


def spread_dict(expr: Expr) -> Spread:
	"""Wrap a spread expression with Map-to-object conversion.

	Python dicts transpile to Map, which has no enumerable own properties.
	This wraps the spread with an IIFE that converts Map to object:
		(...expr) -> ...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(expr)

	The IIFE ensures expr is evaluated only once.
	"""
	s = Identifier("$s")
	is_map = Binary(s, "instanceof", Identifier("Map"))
	as_obj = Call(Member(Identifier("Object"), "fromEntries"), [s])
	return Spread(Call(Arrow(["$s"], Ternary(is_map, as_obj, s)), [expr]))


@dataclass(slots=True)
class New(Expr):
	"""JS new expression: new Ctor(args)"""

	ctor: Expr
	args: Sequence[Expr]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("new ")
		self.ctor.emit(out)
		out.append("(")
		for i, a in enumerate(self.args):
			if i > 0:
				out.append(", ")
			a.emit(out)
		out.append(")")

	@override
	def render(self) -> VDOMExpr:
		return {
			"t": "new",
			"ctor": self.ctor.render(),
			"args": [a.render() for a in self.args],
		}


class TransformerFn(Protocol):
	def __call__(self, *args: Any, ctx: Transpiler, **kwargs: Any) -> Expr: ...


_F = TypeVar("_F", bound=TransformerFn)


@dataclass(slots=True)
class Transformer(Expr, Generic[_F]):
	"""Expr that wraps a function transforming args to Expr output.

	Used for Python->JS transpilation of functions, builtins, and module attrs.
	The wrapped function receives args/kwargs and ctx, and returns an Expr.

	Example:
		emit_len = Transformer(lambda x, ctx: Member(ctx.emit_expr(x), "length"), name="len")
		# When called: emit_len.transpile_call([some_ast], {}, ctx) -> Member(some_expr, "length")
	"""

	fn: _F
	name: str = ""  # For error messages

	@override
	def emit(self, out: list[str]) -> None:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot be emitted directly - must be called")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		# Convert keywords to dict, reject spreads
		kwargs: dict[str, ast.expr] = {}
		for kw in keywords:
			if kw.arg is None:
				label = self.name or "Function"
				raise TranspileError(f"{label} does not support **spread")
			kwargs[kw.arg] = kw.value
		if kwargs:
			return self.fn(*args, ctx=ctx, **kwargs)
		return self.fn(*args, ctx=ctx)

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot have attributes")

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot be subscripted")

	@override
	def render(self) -> VDOMExpr:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot be rendered - must be called")


@overload
def transformer(arg: str) -> Callable[[_F], _F]: ...


@overload
def transformer(arg: _F) -> _F: ...


def transformer(arg: str | _F) -> Callable[[_F], _F] | _F:
	"""Decorator/helper for Transformer.

	Usage:
		@transformer("len")
		def emit_len(x, *, ctx): ...
	or:
		emit_len = transformer(lambda x, *, ctx: ...)

	Returns a Transformer, but the type signature lies and preserves
	the original function type.
	"""
	if isinstance(arg, str):

		def decorator(fn: _F) -> _F:
			return cast(_F, Transformer(fn, name=arg))

		return decorator
	elif isfunction(arg):
		# Use empty name for lambdas, function name for named functions
		name = "" if arg.__name__ == "<lambda>" else arg.__name__
		return cast(_F, Transformer(arg, name=name))
	else:
		raise TypeError(
			"transformer expects a function or string (for decorator usage)"
		)


# =============================================================================
# Statement Nodes
# =============================================================================


@dataclass(slots=True)
class Return(Stmt):
	"""JS return statement: return expr;"""

	value: Expr | None = None

	@override
	def emit(self, out: list[str]) -> None:
		out.append("return")
		if self.value is not None:
			out.append(" ")
			self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class If(Stmt):
	"""JS if statement: if (cond) { ... } else { ... }"""

	cond: Expr
	then: Sequence[Stmt]
	else_: Sequence[Stmt] = ()

	@override
	def emit(self, out: list[str]) -> None:
		out.append("if (")
		self.cond.emit(out)
		out.append(") {\n")
		for stmt in self.then:
			stmt.emit(out)
			out.append("\n")
		out.append("}")
		if self.else_:
			out.append(" else {\n")
			for stmt in self.else_:
				stmt.emit(out)
				out.append("\n")
			out.append("}")


@dataclass(slots=True)
class ForOf(Stmt):
	"""JS for-of loop: for (const x of iter) { ... }

	target can be a single name or array pattern for destructuring: [a, b]
	"""

	target: str
	iter: Expr
	body: Sequence[Stmt]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("for (const ")
		out.append(self.target)
		out.append(" of ")
		self.iter.emit(out)
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class While(Stmt):
	"""JS while loop: while (cond) { ... }"""

	cond: Expr
	body: Sequence[Stmt]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("while (")
		self.cond.emit(out)
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class Break(Stmt):
	"""JS break statement."""

	@override
	def emit(self, out: list[str]) -> None:
		out.append("break;")


@dataclass(slots=True)
class Continue(Stmt):
	"""JS continue statement."""

	@override
	def emit(self, out: list[str]) -> None:
		out.append("continue;")


@dataclass(slots=True)
class Assign(Stmt):
	"""JS assignment: let x = expr; or x = expr; or x += expr;

	declare: "let", "const", or None (reassignment)
	op: None for =, or "+", "-", etc. for augmented assignment
	"""

	target: str | Expr
	value: Expr
	declare: Lit["let", "const"] | None = None
	op: str | None = None  # For augmented: +=, -=, etc.

	@override
	def emit(self, out: list[str]) -> None:
		if self.declare:
			out.append(self.declare)
			out.append(" ")
		if isinstance(self.target, str):
			out.append(self.target)
		else:
			_emit_primary(self.target, out)
		if self.op:
			out.append(" ")
			out.append(self.op)
			out.append("= ")
		else:
			out.append(" = ")
		self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class ExprStmt(Stmt):
	"""JS expression statement: expr;"""

	expr: Expr

	@override
	def emit(self, out: list[str]) -> None:
		self.expr.emit(out)
		out.append(";")


@dataclass(slots=True)
class Block(Stmt):
	"""JS block: { ... } - a sequence of statements."""

	body: Sequence[Stmt]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("{\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class StmtSequence(Stmt):
	"""A sequence of statements without block braces.

	Used for tuple unpacking where we need multiple statements
	but don't want to create a new scope.
	"""

	body: Sequence[Stmt]

	@override
	def emit(self, out: list[str]) -> None:
		for i, stmt in enumerate(self.body):
			stmt.emit(out)
			if i < len(self.body) - 1:
				out.append("\n")


@dataclass(slots=True)
class Throw(Stmt):
	"""JS throw statement: throw expr;"""

	value: Expr

	@override
	def emit(self, out: list[str]) -> None:
		out.append("throw ")
		self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class TryStmt(Stmt):
	"""JS try/catch/finally statement.

	try { body } catch (param) { handler } finally { finalizer }
	"""

	body: Sequence[Stmt]
	catch_param: str | None = None  # None for bare except
	catch_body: Sequence[Stmt] | None = None
	finally_body: Sequence[Stmt] | None = None

	@override
	def emit(self, out: list[str]) -> None:
		out.append("try {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")

		if self.catch_body is not None:
			if self.catch_param:
				out.append(f" catch ({self.catch_param}) {{\n")
			else:
				out.append(" catch {\n")
			for stmt in self.catch_body:
				stmt.emit(out)
				out.append("\n")
			out.append("}")

		if self.finally_body is not None:
			out.append(" finally {\n")
			for stmt in self.finally_body:
				stmt.emit(out)
				out.append("\n")
			out.append("}")


@dataclass(slots=True)
class Function(Expr):
	"""JS function: function name(params) { ... } or async function ...

	For statement-bodied functions. Use Arrow for expression-bodied.
	"""

	params: Sequence[str]
	body: Sequence[Stmt]
	name: str | None = None
	is_async: bool = False

	@override
	def emit(self, out: list[str]) -> None:
		if self.is_async:
			out.append("async ")
		out.append("function")
		if self.name:
			out.append(" ")
			out.append(self.name)
		out.append("(")
		out.append(", ".join(self.params))
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")

	@override
	def render(self) -> VDOMExpr:
		raise TypeError("Function cannot be rendered as VDOMExpr")


Node: TypeAlias = Primitive | Expr | PulseNode
Child: TypeAlias = Node | Iterable[Node]
Children: TypeAlias = Sequence[Child]
Prop: TypeAlias = Primitive | Expr


# =============================================================================
# Emit logic
# =============================================================================


Emittable: TypeAlias = Expr | Stmt


def emit(node: Emittable) -> str:
	"""Emit an expression or statement as JavaScript/JSX code."""
	out: list[str] = []
	node.emit(out)
	return "".join(out)


# Operator precedence table (higher = binds tighter)
_PRECEDENCE: dict[str, int] = {
	# Primary
	".": 20,
	"[]": 20,
	"()": 20,
	# Unary
	"!": 17,
	"+u": 17,
	"-u": 17,
	"typeof": 17,
	"await": 17,
	# Exponentiation (right-assoc)
	"**": 16,
	# Multiplicative
	"*": 15,
	"/": 15,
	"%": 15,
	# Additive
	"+": 14,
	"-": 14,
	# Relational
	"<": 12,
	"<=": 12,
	">": 12,
	">=": 12,
	"===": 12,
	"!==": 12,
	"instanceof": 12,
	"in": 12,
	# Logical
	"&&": 7,
	"||": 6,
	"??": 6,
	# Ternary
	"?:": 4,
	# Comma
	",": 1,
}

_RIGHT_ASSOC = {"**"}


def _escape_string(s: str) -> str:
	"""Escape for double-quoted JS string literals."""
	return (
		s.replace("\\", "\\\\")
		.replace('"', '\\"')
		.replace("\n", "\\n")
		.replace("\r", "\\r")
		.replace("\t", "\\t")
		.replace("\b", "\\b")
		.replace("\f", "\\f")
		.replace("\v", "\\v")
		.replace("\x00", "\\x00")
		.replace("\u2028", "\\u2028")
		.replace("\u2029", "\\u2029")
	)


def _escape_template(s: str) -> str:
	"""Escape for template literal strings."""
	return (
		s.replace("\\", "\\\\")
		.replace("`", "\\`")
		.replace("${", "\\${")
		.replace("\n", "\\n")
		.replace("\r", "\\r")
		.replace("\t", "\\t")
		.replace("\b", "\\b")
		.replace("\f", "\\f")
		.replace("\v", "\\v")
		.replace("\x00", "\\x00")
		.replace("\u2028", "\\u2028")
		.replace("\u2029", "\\u2029")
	)


def _escape_jsx_text(s: str) -> str:
	"""Escape text content for JSX."""
	return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_jsx_attr(s: str) -> str:
	"""Escape attribute value for JSX."""
	return s.replace("&", "&amp;").replace('"', "&quot;")


def _emit_paren(node: Expr, parent_op: str, side: str, out: list[str]) -> None:
	"""Emit child with parens if needed for precedence."""
	# Ternary as child of binary always needs parens
	needs_parens = False
	if isinstance(node, Ternary):
		needs_parens = True
	else:
		child_prec = node.precedence()
		parent_prec = _PRECEDENCE.get(parent_op, 0)
		if child_prec < parent_prec:
			needs_parens = True
		elif child_prec == parent_prec and isinstance(node, Binary):
			# Handle associativity
			if parent_op in _RIGHT_ASSOC:
				needs_parens = side == "left"
			else:
				needs_parens = side == "right"

	if needs_parens:
		out.append("(")
		node.emit(out)
		out.append(")")
	else:
		node.emit(out)


def _emit_primary(node: Expr, out: list[str]) -> None:
	"""Emit with parens if not primary precedence."""
	if node.precedence() < 20 or isinstance(node, Ternary):
		out.append("(")
		node.emit(out)
		out.append(")")
	else:
		node.emit(out)


def _emit_value(value: Any, out: list[str]) -> None:
	"""Emit a Python value as JavaScript literal."""
	if value is None:
		out.append("null")
	elif isinstance(value, bool):
		out.append("true" if value else "false")
	elif isinstance(value, str):
		out.append('"')
		out.append(_escape_string(value))
		out.append('"')
	elif isinstance(value, (int, float)):
		out.append(str(value))
	elif isinstance(value, dt.datetime):
		out.append("new Date(")
		out.append(str(int(value.timestamp() * 1000)))
		out.append(")")
	elif isinstance(value, list):
		out.append("[")
		for i, v in enumerate(value):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			_emit_value(v, out)
		out.append("]")
	elif isinstance(value, dict):
		out.append("{")
		for i, (k, v) in enumerate(value.items()):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			out.append('"')
			out.append(_escape_string(str(k)))  # pyright: ignore[reportUnknownArgumentType]
			out.append('": ')
			_emit_value(v, out)
		out.append("}")
	elif isinstance(value, set):
		out.append("new Set([")
		for i, v in enumerate(value):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			_emit_value(v, out)
		out.append("])")
	else:
		raise TypeError(f"Cannot emit {type(value).__name__} as JavaScript")


def _emit_jsx_prop(name: str, value: Prop, out: list[str]) -> None:
	"""Emit a single JSX prop."""
	# Spread props
	if isinstance(value, Spread):
		out.append("{...")
		value.expr.emit(out)
		out.append("}")
		return
	# Expression nodes
	if isinstance(value, Expr):
		# String literals can use compact form
		if isinstance(value, Literal) and isinstance(value.value, str):
			out.append(name)
			out.append('="')
			out.append(_escape_jsx_attr(value.value))
			out.append('"')
		else:
			out.append(name)
			out.append("={")
			value.emit(out)
			out.append("}")
		return
	# Primitives
	if value is None:
		out.append(name)
		out.append("={null}")
		return
	if isinstance(value, bool):
		out.append(name)
		out.append("={true}" if value else "={false}")
		return
	if isinstance(value, str):
		out.append(name)
		out.append('="')
		out.append(_escape_jsx_attr(value))
		out.append('"')
		return
	if isinstance(value, (int, float)):
		out.append(name)
		out.append("={")
		out.append(str(value))
		out.append("}")
		return
	# Value
	if isinstance(value, Value):
		out.append(name)
		out.append("={")
		_emit_value(value.value, out)
		out.append("}")
		return
	# Nested Element (render prop)
	if isinstance(value, Element):
		out.append(name)
		out.append("={")
		value.emit(out)
		out.append("}")
		return
	# Callable - error
	if callable(value):
		raise TypeError("Cannot emit callable in transpile context")
	# Fallback for other data
	out.append(name)
	out.append("={")
	_emit_value(value, out)
	out.append("}")


def _emit_jsx_child(child: Node, out: list[str]) -> None:
	"""Emit a single JSX child."""
	# Primitives
	if child is None or isinstance(child, bool):
		return  # React ignores None/bool
	if isinstance(child, str):
		out.append(_escape_jsx_text(child))
		return
	if isinstance(child, (int, float)):
		out.append("{")
		out.append(str(child))
		out.append("}")
		return
	if isinstance(child, dt.datetime):
		out.append("{")
		_emit_value(child, out)
		out.append("}")
		return
	# PulseNode - error
	if isinstance(child, PulseNode):
		fn_name = getattr(child.fn, "__name__", "unknown")
		raise TypeError(
			f"Cannot transpile PulseNode '{fn_name}'. "
			+ "Server components must be rendered, not transpiled."
		)
	# Element - recurse
	if isinstance(child, Element):
		child.emit(out)
		return
	# Spread - emit as {expr} without the spread operator (arrays are already iterable in JSX)
	if isinstance(child, Spread):
		out.append("{")
		child.expr.emit(out)
		out.append("}")
		return
	# Expr
	if isinstance(child, Expr):
		out.append("{")
		child.emit(out)
		out.append("}")
		return
	# Value
	if isinstance(child, Value):
		out.append("{")
		_emit_value(child.value, out)
		out.append("}")
		return
	raise TypeError(f"Cannot emit {type(child).__name__} as JSX child")
