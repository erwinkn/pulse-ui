# ============================================================================
# React Component Integration
# ============================================================================

import inspect
import typing
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
from functools import cache
from inspect import Parameter
from types import UnionType
from typing import (
	Annotated,
	Any,
	Generic,
	Literal,
	ParamSpec,
	TypeVar,
	Unpack,
	cast,
	get_args,
	get_origin,
	override,
)

from pulse.codegen.imports import Import, ImportStatement
from pulse.helpers import Sentinel
from pulse.reactive_extensions import unwrap
from pulse.vdom import Child, Element, Node

T = TypeVar("T")
P = ParamSpec("P")
DEFAULT: Any = Sentinel("DEFAULT")


# ----------------------------------------------------------------------------
# Detection for stringified annotations (from __future__ import annotations)
# ----------------------------------------------------------------------------


def _function_has_string_annotations(fn: Callable[..., Any]) -> bool:
	"""Return True if any function annotations are strings.

	This happens when the defining module uses `from __future__ import annotations`.
	In that case, resolving types at runtime is fragile; we skip PropSpec building.
	"""
	try:
		anns = getattr(fn, "__annotations__", {}) or {}
		return any(isinstance(v, str) for v in anns.values())
	except Exception:
		return False


def _is_any_annotation(annotation: object) -> bool:
	"""Return True when an annotation is effectively `typing.Any`."""
	try:
		return annotation is Any or annotation == Any
	except TypeError:
		return False


class Prop(Generic[T]):
	default: T | None
	required: bool
	default_factory: Callable[[], T] | None
	serialize: Callable[[T], Any] | None
	map_to: str | None
	typ_: type | tuple[type, ...] | None

	def __init__(
		self,
		default: T | None = DEFAULT,
		# Will be set by all the conventional ways of defining PropSpec
		required: bool = DEFAULT,  # type: ignore
		default_factory: Callable[[], T] | None = None,
		serialize: Callable[[T], Any] | None = None,
		map_to: str | None = None,
		typ_: type | tuple[type, ...] | None = None,
	) -> None:
		self.default = default
		self.required = required
		self.default_factory = default_factory
		self.serialize = serialize
		self.map_to = map_to
		self.typ_ = typ_

	@override
	def __repr__(self) -> str:
		def _callable_name(fn: Callable[..., Any] | None) -> str:
			if fn is None:
				return "None"
			return getattr(fn, "__name__", fn.__class__.__name__)

		parts: list[str] = []
		if self.typ_:
			parts.append(f"type={_format_runtime_type(self.typ_)}")
		if self.required is not DEFAULT:
			parts.append(f"required={self.required}")
		if self.default is not None:
			parts.append(f"default={self.default!r}")
		if self.default_factory is not None:
			parts.append(f"default_factory={_callable_name(self.default_factory)}")
		if self.serialize is not None:
			parts.append(f"serialize={_callable_name(self.serialize)}")
		if self.map_to is not None:
			parts.append(f"map_to={self.map_to!r}")
		return f"Prop({', '.join(parts)})"


def prop(
	default: T = DEFAULT,
	*,
	default_factory: Callable[[], T] | None = None,
	serialize: Callable[[T], Any] | None = None,
	map_to: str | None = None,
) -> T:
	"""
	Convenience constructor for Prop to be used inside TypedDict defaults.
	"""
	return Prop(  # pyright: ignore[reportReturnType]
		default=default,
		default_factory=default_factory,
		serialize=serialize,
		map_to=map_to,
	)


class PropSpec:
	allow_unspecified: bool

	def __init__(
		self,
		required: dict[str, Prop[Any]],
		optional: dict[str, Prop[Any]],
		allow_unspecified: bool = False,
	) -> None:
		if "key" in required or "key" in optional:
			raise ValueError(
				"'key' is a reserved prop, please use another name (like 'id', 'label', or even 'key_')"
			)
		self.required: dict[str, Prop[Any]] = required
		self.optional: dict[str, Prop[Any]] = optional
		self.allow_unspecified = allow_unspecified
		# Precompute optional keys that provide defaults so we can apply them
		# without scanning all optional props on every apply call.
		self._optional_with_defaults: tuple[str, ...] = tuple(
			k
			for k, p in optional.items()
			if (p.default is not DEFAULT) or (p.default_factory is not None)
		)

	@override
	def __repr__(self) -> str:
		keys_list = list(self.keys())
		keys_preview = ", ".join(keys_list[:5])
		if len(keys_list) > 5:
			keys_preview += ", ..."
		return f"Props(keys=[{keys_preview}])"

	def as_dict(self) -> dict[str, Prop[Any]]:
		"""Return a merged dict of required and optional props."""
		return self.required | self.optional

	def __getitem__(self, key: str) -> Prop[Any]:
		if key in self.required:
			return self.required[key]
		if key in self.optional:
			return self.optional[key]
		raise KeyError(key)

	def keys(self):
		return self.required.keys() | self.optional.keys()

	def merge(self, other: "PropSpec"):
		conflicts = self.keys() & other.keys()
		if conflicts:
			conflict_list = ", ".join(sorted(conflicts))
			raise ValueError(
				f"Conflicting prop definitions for: {conflict_list}. Define each prop only once across explicit params and Unpack[TypedDict]",
			)
		merged_required = self.required | other.required
		merged_optional = self.optional | other.optional
		return PropSpec(
			required=merged_required,
			optional=merged_optional,
			allow_unspecified=self.allow_unspecified or other.allow_unspecified,
		)

	def apply(self, comp_tag: str, props: dict[str, Any]):
		result: dict[str, Any] = {}
		known_keys = self.keys()

		# Unknown keys handling (exclude 'key' as it's special)
		unknown_keys = props.keys() - known_keys - {"key"}
		if not self.allow_unspecified and unknown_keys:
			bad = ", ".join(repr(k) for k in sorted(unknown_keys))
			raise ValueError(f"Unexpected prop(s) for component '{comp_tag}': {bad}")
		if self.allow_unspecified:
			for k in unknown_keys:
				v = props[k]
				if v is not DEFAULT:
					result[k] = v

		missing_props: list[str] = []
		overlaps: dict[str, list[str]] = defaultdict(list)

		# 1) Apply required props (including their defaults if provided)
		for py_key, prop in self.required.items():
			p = prop if isinstance(prop, Prop) else Prop(typ_=prop)
			if py_key in props:
				value = props[py_key]
			elif p.default_factory is not None:
				value = p.default_factory()
			else:
				value = p.default

			if value is DEFAULT:
				missing_props.append(py_key)
				continue

			if p.serialize is not None:
				value = p.serialize(value)

			js_key = p.map_to or py_key
			if js_key in result:
				overlaps[js_key].append(py_key)
				continue
			result[js_key] = value

		# 2) Apply provided optional props (only those present)
		provided_known_optional = props.keys() & self.optional.keys()
		for py_key in provided_known_optional:
			prop = self.optional[py_key]
			p = prop if isinstance(prop, Prop) else Prop(typ_=prop)
			value = props[py_key]

			if value is DEFAULT:
				# Omit optional prop when DEFAULT sentinel is used
				continue

			if p.serialize is not None:
				value = p.serialize(value)

			js_key = p.map_to or py_key
			if js_key in result:
				overlaps[js_key].append(py_key)
				continue
			result[js_key] = value

		# 3) Apply optional props that have defaults and were not provided
		for py_key in self._optional_with_defaults:
			if py_key in props:
				continue
			prop = self.optional[py_key]
			p = prop if isinstance(prop, Prop) else Prop(typ_=prop)
			if p.default_factory is not None:
				value = p.default_factory()
			else:
				value = p.default

			if value is DEFAULT:
				continue

			if p.serialize is not None:
				value = p.serialize(value)

			js_key = p.map_to or py_key
			if js_key in result:
				overlaps[js_key].append(py_key)
				continue
			result[js_key] = value

		if missing_props or overlaps:
			errors: list[str] = []
			if missing_props:
				errors.append(f"Missing required props: {', '.join(missing_props)}")
			if overlaps:
				for js_key, py_keys in overlaps.items():
					errors.append(
						f"Multiple props map to '{js_key}': {', '.join(py_keys)}"
					)
			raise ValueError(
				f"Invalid props for component '{comp_tag}': {'; '.join(errors)}"
			)

		return result or None


def default_signature(
	*children: Child, key: str | None = None, **props: Any
) -> Element: ...
def default_fn_signature_without_children(
	key: str | None = None, **props: Any
) -> Element: ...


class ReactComponent(Generic[P], Import):
	"""
	A React component that can be used within the UI tree.
	Returns a function that creates mount point UITreeNode instances.

	Args:
	    tag: Name of the component (or "default" for default export)
	    import_path: Module path to import the component from
	    alias: Optional alias for the component in the registry
	    is_default: True if this is a default export, else named export
	    import_name: If specified, import this name from import_path and access tag as a property of it

	Returns:
	    A function that creates Node instances with mount point tags
	"""

	props_spec: PropSpec
	fn_signature: Callable[P, Element]
	lazy: bool

	def __init__(
		self,
		name: str,
		src: str,
		*,
		is_default: bool = False,
		prop: str | None = None,
		lazy: bool = False,
		version: str | None = None,
		prop_spec: PropSpec | None = None,
		fn_signature: Callable[P, Element] = default_signature,
		extra_imports: tuple[ImportStatement, ...]
		| list[ImportStatement]
		| None = None,
	):
		kind = "default" if is_default else "named"
		super().__init__(name, src, kind, prop=prop)

		# Build props_spec from fn_signature if provided and props not provided
		if prop_spec:
			self.props_spec = prop_spec
		elif fn_signature not in (
			default_signature,
			default_fn_signature_without_children,
		):
			self.props_spec = parse_fn_signature(fn_signature)
		else:
			self.props_spec = PropSpec({}, {}, allow_unspecified=True)

		self.fn_signature = fn_signature
		self.lazy = lazy
		# Optional npm semver constraint for this component's package
		self.version: str | None = version
		# Additional import statements to include in route where this component is used
		self.extra_imports: list[ImportStatement] = list(extra_imports or [])
		COMPONENT_REGISTRY.get().add(self)

	@override
	def __repr__(self) -> str:
		default_part = ", default=True" if self.is_default else ""
		prop_part = f", prop='{self.prop}'" if self.prop else ""
		lazy_part = ", lazy=True" if self.lazy else ""
		props_part = f", props_spec={self.props_spec!r}"
		return f"ReactComponent(name='{self.name}', src='{self.src}'{prop_part}{default_part}{lazy_part}{props_part})"

	def __call__(self, *children: P.args, **props: P.kwargs) -> Node:
		key = props.get("key")
		if key is not None and not isinstance(key, str):
			raise ValueError("key must be a string or None")
		# Apply optional props specification: fill defaults, enforce required,
		# run serializers, and remap keys.
		real_props = self.props_spec.apply(self.name, props)
		if real_props:
			real_props = {key: unwrap(value) for key, value in real_props.items()}

		return Node(
			tag=f"$${self.expr}",
			key=key,
			props=real_props,
			children=cast(tuple[Child], children),
		)


def parse_fn_signature(fn: Callable[..., Any]) -> PropSpec:
	"""Parse a function signature into a Props spec using a single pass.

	Rules:
	- May accept var-positional children `*children` (if annotated, must be Child)
	- Must define `key: Optional[str] = None` (keyword-accepting)
	- Other props may be explicit keyword params and/or via **props: Unpack[TypedDict]
	- A prop may not be specified both explicitly and in the Unpack
	- Annotated[..., Prop(...)] on parameters is disallowed (use default Prop instead)
	"""

	# If annotations are stringified, skip building and allow unspecified props.
	if _function_has_string_annotations(fn):
		return PropSpec({}, {}, allow_unspecified=True)

	sig = inspect.signature(fn)
	params = list(sig.parameters.values())

	explicit_required: dict[str, Prop[Any]] = {}
	explicit_optional: dict[str, Prop[Any]] = {}
	explicit_order: list[str] = []
	explicit_spec: PropSpec
	unpack_spec: PropSpec

	var_positional: Parameter | None = None
	var_kw: Parameter | None = None
	key: Parameter | None = None

	# One pass: collect structure and build explicit spec as we go
	for p in params:
		# Disallow positional-only parameters
		if p.kind is Parameter.POSITIONAL_ONLY:
			raise ValueError(
				"Function must not declare positional-only parameters besides *children",
			)

		if p.kind is Parameter.VAR_POSITIONAL:
			var_positional = p
			continue

		if p.kind is Parameter.VAR_KEYWORD:
			var_kw = p
			continue

		if p.name == "key":
			key = p
			continue

		# For regular params, forbid additional required positionals
		if p.kind is Parameter.POSITIONAL_OR_KEYWORD and p.default is Parameter.empty:
			raise ValueError(
				"Function signature must not declare additional required positional parameters; only *children is allowed for positionals",
			)

		if p.kind not in (
			Parameter.POSITIONAL_OR_KEYWORD,
			Parameter.KEYWORD_ONLY,
		):
			continue

		# Build explicit spec (skip 'key' handled above)
		annotation = p.annotation if p.annotation is not Parameter.empty else Any
		origin = get_origin(annotation)
		annotation_args = get_args(annotation)

		# Disallow Annotated[..., Prop(...)] on parameters
		if (
			origin is Annotated
			and annotation_args
			and any(isinstance(m, Prop) for m in annotation_args[1:])
		):
			raise TypeError(
				"Annotated[..., ps.prop(...)] is not allowed on function parameters; use a default `= ps.prop(...)` or a TypedDict",
			)

		runtime_type = _annotation_to_runtime_type(
			annotation_args[0]
			if origin is Annotated and annotation_args
			else annotation
		)

		if isinstance(p.default, Prop):
			prop = p.default
			if prop.typ_ is None:
				prop.typ_ = runtime_type
			# Has default via Prop -> optional
			explicit_optional[p.name] = prop
			explicit_order.append(p.name)
		elif p.default is not Parameter.empty:
			prop = Prop(default=p.default, required=False, typ_=runtime_type)
			explicit_optional[p.name] = prop
			explicit_order.append(p.name)
		else:
			prop = Prop(typ_=runtime_type)
			# No default -> required
			prop.required = True
			explicit_required[p.name] = prop
			explicit_order.append(p.name)

	explicit_spec = PropSpec(
		explicit_required,
		explicit_optional,
	)

	# Validate *children annotation if present
	if var_positional is not None:
		annotation = var_positional.annotation
		if (
			annotation is not Parameter.empty
			and annotation is not Child
			and not _is_any_annotation(annotation)
		):
			raise TypeError(
				f"*{var_positional.name} must be annotated as `*{var_positional.name}: ps.Child`"
			)

	# Validate `key`` argument
	if key is None:
		raise ValueError("Function must define a `key: str | None = None` parameter")
	if key.default is not None:
		raise ValueError("'key' parameter must default to None")
	if key.kind not in (
		Parameter.KEYWORD_ONLY,
		Parameter.POSITIONAL_OR_KEYWORD,
	):
		raise ValueError("'key' parameter must be a keyword argument")

	# Parse **props as Unpack[TypedDict]
	unpack_spec = parse_typed_dict_props(var_kw)

	return unpack_spec.merge(explicit_spec)


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
# Utilities: Build Props specs from TypedDict definitions
# ----------------------------------------------------------------------------


def _is_typeddict_type(cls: type) -> bool:
	"""Best-effort detection for TypedDict types across Python versions."""
	return isinstance(getattr(cls, "__annotations__", None), dict) and getattr(
		cls, "__total__", None
	) in (True, False)


def _unwrap_required_notrequired(annotation: Any) -> tuple[Any, bool | None]:
	"""
	If annotation is typing.Required[T] or typing.NotRequired[T], return (T, required?).
	Otherwise return (annotation, None).
	"""

	origin = get_origin(annotation)
	if origin is typing.Required:
		args = get_args(annotation)
		inner = args[0] if args else Any
		return inner, True
	if origin is typing.NotRequired:
		args = get_args(annotation)
		inner = args[0] if args else Any
		return inner, False
	return annotation, None


@cache
def _annotation_to_runtime_type(annotation: Any) -> type | tuple[type, ...]:
	"""
	Convert a typing annotation into a runtime-checkable class or tuple of classes
	suitable for isinstance(). This is intentionally lossy but practical.
	"""
	# Unwrap Required/NotRequired
	annotation, _ = _unwrap_required_notrequired(annotation)

	origin = get_origin(annotation)
	args = get_args(annotation)

	# Any -> accept anything
	if annotation is Any:
		return object

	# Annotated[T, ...] -> T
	if origin is Annotated and args:
		return _annotation_to_runtime_type(args[0])

	# Optional[T] / Union[...] / X | Y
	if origin is UnionType:
		# Fallback for some Python versions where get_origin may be odd
		union_args = args or getattr(annotation, "__args__", ())
		runtime_types: list[type] = []
		for a in union_args:
			rt = _annotation_to_runtime_type(a)
			if isinstance(rt, tuple):
				runtime_types.extend(rt)
			elif isinstance(rt, type):
				runtime_types.append(rt)
		# Deduplicate while preserving order
		out: list[type] = []
		for t in runtime_types:
			if t not in out:
				out.append(t)
		return tuple(out) if len(out) > 1 else (out[0] if out else object)

	# Literal[...] -> base types of provided literals
	if origin is Literal:
		literal_types: set[type] = {type(v) for v in args}
		# None appears as NoneType
		if len(literal_types) == 0:
			return object
		if len(literal_types) == 1:
			return next(iter(literal_types))
		return tuple(literal_types)

	# Parametrized containers -> use their builtin origins for isinstance
	if origin in (list, dict, set, tuple):
		return cast(type | tuple[type, ...], origin)

	# TypedDict nested -> treat as dict
	if isinstance(annotation, type) and _is_typeddict_type(annotation):
		return dict

	# Direct classes
	if isinstance(annotation, type):
		return annotation

	# Fallback: accept anything
	return object


def _extract_prop_from_annotated(annotation: Any) -> tuple[Any, Prop[Any] | None]:
	"""
	If annotation is Annotated[T, ...] and any metadata item is a Prop, return (T, Prop).
	Otherwise return (annotation, None).
	"""
	origin = get_origin(annotation)
	args = get_args(annotation)
	if origin is Annotated and args:
		base = args[0]
		meta = args[1:]
		for m in meta:
			if isinstance(m, Prop):
				return base, m
	return annotation, None


def _clone_prop(p: Prop[Any]) -> Prop[Any]:
	"""Shallow clone a Prop to avoid sharing instances across cached specs."""
	return Prop(
		default=p.default,
		required=p.required,
		default_factory=p.default_factory,
		serialize=p.serialize,
		map_to=p.map_to,
		typ_=p.typ_,
	)


def _typed_dict_bases(typed_dict_cls: type) -> list[type]:
	return [
		b for b in getattr(typed_dict_cls, "__bases__", ()) if _is_typeddict_type(b)
	]


@cache
def prop_spec_from_typeddict(typed_dict_cls: type) -> PropSpec:
	"""Build and cache a Props spec from a TypedDict class tree.

	Caches by the TypedDict class object (stable and hashable). This speeds up
	repeated reuse of common props like HTMLProps and HTMLAnchorProps across many
	component definitions.
	"""
	annotations: dict[str, Any] = getattr(typed_dict_cls, "__annotations__", {})
	# If TypedDict annotations are stringified, skip building and allow unspecified.
	if annotations and any(isinstance(v, str) for v in annotations.values()):
		return PropSpec({}, {}, allow_unspecified=True)
	required_keys: set[str] | None = getattr(typed_dict_cls, "__required_keys__", None)
	is_total: bool = bool(getattr(typed_dict_cls, "__total__", True))

	# 1) Merge cached specs from TypedDict base classes (preserve insertion order)
	merged: dict[str, Prop[Any]] = {}
	for base in _typed_dict_bases(typed_dict_cls):
		base_spec = prop_spec_from_typeddict(base)
		for k, p in base_spec.as_dict().items():
			merged[k] = _clone_prop(p)

	# 2) Add/override keys declared locally on this class in definition order.
	#    If a key exists in a base, this intentionally shadows the base entry.
	for key in annotations.keys():
		annotation = annotations[key]
		# First see if runtime provides explicit required/optional wrappers
		annotation, _annotation_required = _unwrap_required_notrequired(annotation)
		# Extract Prop metadata from Annotated if present
		annotation, annotation_prop = _extract_prop_from_annotated(annotation)

		runtime_type = _annotation_to_runtime_type(annotation)
		prop = annotation_prop or Prop()
		if prop.required is not DEFAULT:
			raise TypeError(
				"Use total=True + NotRequired[T] or total=False + Required[T] to define required and optional props within a TypedDict"
			)
		prop.typ_ = runtime_type
		merged[key] = prop

	# 3) Finalize required flags per this class's semantics
	if required_keys is not None:
		for k, p in merged.items():
			p.required = k in required_keys
	else:
		# Fallback: infer via wrappers if available; otherwise default to class total
		for k, p in merged.items():
			ann = annotations.get(k, None)
			if ann is not None:
				_, req = _unwrap_required_notrequired(ann)
				if req is not None:
					p.required = req
					continue
			p.required = is_total

	# Split into required/optional
	required: dict[str, Prop[Any]] = {}
	optional: dict[str, Prop[Any]] = {}
	for k, p in merged.items():
		if p.required is True:
			required[k] = p
		else:
			optional[k] = p

	return PropSpec(required, optional)


def parse_typed_dict_props(var_kw: Parameter | None) -> PropSpec:
	"""
	Build a Props spec from a TypedDict class.

	- Required vs optional is inferred from __required_keys__/__optional_keys__ when
	  available, otherwise from Required/NotRequired wrappers or the class __total__.
	- Types are converted to runtime-checkable types for isinstance checks.
	"""
	# No **props -> no keyword arguments defined here
	if not var_kw:
		return PropSpec({}, {})

	# Untyped **props -> allow all
	annot = var_kw.annotation
	if annot in (None, Parameter.empty):
		return PropSpec({}, {}, allow_unspecified=True)
	if _is_any_annotation(annot):
		return PropSpec({}, {}, allow_unspecified=True)
	# Stringified annotations like "Unpack[Props]" are too fragile to parse.
	if isinstance(annot, str):
		return PropSpec({}, {}, allow_unspecified=True)

	# From here, we should have **props: Unpack[MyProps] where MyProps is a TypedDict
	origin = get_origin(annot)
	if origin is not Unpack:
		raise TypeError(
			"**props must be annotated as typing.Unpack[Props] where Props is a TypedDict"
		)
	unpack_args = get_args(annot)
	if not unpack_args:
		raise TypeError("Unpack must wrap a TypedDict class, e.g., Unpack[MyProps]")
	typed_arg = unpack_args[0]

	# Handle parameterized TypedDicts like MyProps[T] or MyProps[int]
	# typing.get_origin returns the underlying class for parameterized generics
	origin_td = get_origin(typed_arg) or typed_arg

	if not isinstance(origin_td, type) or not _is_typeddict_type(origin_td):
		raise TypeError("Unpack must wrap a TypedDict class, e.g., Unpack[MyProps]")

	# NOTE: For TypedDicts, the annotations contain the fields of all classes in
	# the hierarchy, we don't need to walk the MRO. Use cached builder.
	return prop_spec_from_typeddict(origin_td)


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
	extra_imports: list[ImportStatement] | None = None,
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


# ----------------------------------------------------------------------------
# Helpers for display of runtime types
# ----------------------------------------------------------------------------


def _format_runtime_type(t: type | tuple[type, ...]) -> str:
	if isinstance(t, tuple):
		return "(" + ", ".join(_format_runtime_type(x) for x in t) + ")"
	if isinstance(t, type):
		return getattr(t, "__name__", repr(t))
	return repr(t)
