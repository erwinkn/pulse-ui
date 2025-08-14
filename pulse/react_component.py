# ============================================================================
# React Component Integration
# ============================================================================

from collections import defaultdict
import inspect
from contextvars import ContextVar
from typing import (
    Annotated,
    Any,
    Callable,
    Generic,
    Literal,
    Mapping,
    Optional,
    ParamSpec,
    TypeVar,
    Unpack,
    Union,
    cast,
    get_args,
    get_origin,
)
from types import UnionType
import typing

from pulse.vdom import Node, NodeTree


T = TypeVar("T")
# used when we need to distinguish between an unspecified value and None
MISSING = object()


class Prop(Generic[T]):
    def __init__(
        self,
        default: Optional[T] = MISSING,
        required: bool = MISSING,  # type: ignore
        default_factory: Optional[Callable[[], T]] = None,
        serialize: Optional[Callable[[T], Any]] = None,
        map_to: Optional[str] = None,
        _type: Optional[type | tuple[type, ...]] = None,
    ) -> None:
        self.default = default
        self.required = required
        self.default_factory = default_factory
        self.serialize = serialize
        self.map_to = map_to
        self._type = _type

    def __repr__(self) -> str:
        def _callable_name(fn: Callable[..., Any] | None) -> str:
            if fn is None:
                return "None"
            return getattr(fn, "__name__", fn.__class__.__name__)

        parts: list[str] = []
        if self._type:
            parts.append(f"type={_format_runtime_type(self._type)}")
        if self.required is not None:
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
    default: T = MISSING,
    *,
    default_factory: Optional[Callable[[], T]] = None,
    serialize: Optional[Callable[[T], Any]] = None,
    map_to: Optional[str] = None,
    required=True,
) -> Prop[T]:
    """
    Convenience constructor for Prop to be used inside TypedDict defaults.
    """
    return Prop(
        default=default,
        default_factory=default_factory,
        required=required,
        serialize=serialize,
        map_to=map_to,
    )


class PropSpec:
    spec: dict[str, Prop]

    def __init__(
        self,
        spec: Mapping[str, type | Prop],
        total=True,
        allow_unspecified=False,
        _skip_validation=False,
    ) -> None:
        if "key" in spec:
            raise ValueError(
                "'key' is a reserved prop, please use another name (like 'id', 'label', or even 'key_')"
            )
        self.allow_unspecified = allow_unspecified
        # spec maps canonical python prop name -> Prop or type
        if _skip_validation:
            self.spec = spec  # type: ignore
        else:
            self.spec = {}
            for k, prop in spec.items():
                if not isinstance(prop, Prop):
                    prop = Prop(prop)
                if prop.required is MISSING:
                    prop.required = total
                self.spec[k] = prop

    def __repr__(self) -> str:
        keys_preview = ", ".join(list(self.spec.keys())[:5])
        if len(self.spec) > 5:
            keys_preview += ", ..."
        return f"Props(keys=[{keys_preview}])"

    def merge(self, other: "PropSpec"):
        conflicts = self.spec.keys() & other.spec.keys()
        if conflicts:
            conflict_list = ", ".join(sorted(conflicts))
            raise ValueError(
                f"Conflicting prop definitions for: {conflict_list}. Define each prop only once across explicit params and Unpack[TypedDict]",
            )
        return PropSpec(
            self.spec | other.spec,
            allow_unspecified=self.allow_unspecified or other.allow_unspecified,
            _skip_validation=True,
        )

    def apply(self, comp_key: str, props: dict[str, Any]):
        # Flag unknown props
        if not self.allow_unspecified:
            unknown_keys = props.keys() - self.spec.keys()
            if unknown_keys:
                valid = ", ".join(sorted(self.spec.keys())) or "<none>"
                bad = ", ".join(repr(k) for k in unknown_keys)
                raise ValueError(
                    f"Unexpected prop(s) for component '{comp_key}': {bad}. Valid props: {valid}"
                )

        result: dict[str, Any] = {}
        missing_props = []
        overlaps: dict[str, list[str]] = defaultdict(list)
        for py_key, prop in self.spec.items():
            if not isinstance(prop, Prop):
                prop = Prop(type_=prop)

            # Resolve value + defaults
            if py_key in props:
                value = props[py_key]
            elif prop.default_factory:
                value = prop.default_factory()
            else:
                value = prop.default

            # None could be a valid value or default, which is why we use the
            # "sentinel pattern" of a MISSING object.
            if value is MISSING and prop.required:
                missing_props.append(py_key)
                continue

            if prop.serialize:
                value = prop.serialize(value)

            js_key = prop.map_to or py_key
            if js_key in result:
                overlaps[js_key].append(py_key)
                continue

            result[js_key] = value

        if missing_props or overlaps:
            errors = []
            if missing_props:
                errors.append(f"Missing required props: {', '.join(missing_props)}")
            if overlaps:
                for js_key, py_keys in overlaps.items():
                    errors.append(
                        f"Multiple props map to '{js_key}': {', '.join(py_keys)}"
                    )
            raise ValueError(
                f"Invalid props for component '{comp_key}': {'; '.join(errors)}"
            )

        return result


P = ParamSpec("P")
MISSING = object()  # used to detect whether a default was specified ()


def default_signature(
    *children: NodeTree, key: Optional[str] = None, **props
) -> NodeTree: ...
def default_fn_signature_without_children(
    key: Optional[str] = None, **props
) -> NodeTree: ...


class ReactComponent(Generic[P]):
    """
    A React component that can be used within the UI tree.
    Returns a function that creates mount point UITreeNode instances.

    Args:
        tag: Name of the component (or "default" for default export)
        import_path: Module path to import the component from
        alias: Optional alias for the component in the registry
        is_default: True if this is a default export, else named export

    Returns:
        A function that creates Node instances with mount point tags
    """

    def __init__(
        self,
        tag: str | Literal["default"],
        import_path: str,
        alias: str | None = None,
        is_default=False,
        props: Optional[PropSpec] = None,
        fn_signature: Callable[P, NodeTree] = default_signature,
    ):
        self.tag = tag
        self.key = alias or tag
        self.import_path = import_path
        self.alias = alias
        self.is_default = is_default
        # Build props_spec from fn_signature if provided and props not provided
        if props is None and fn_signature not in (
            default_signature,
            default_fn_signature_without_children,
        ):
            self.props_spec = parse_fn_signature(fn_signature)
        else:
            # Optional runtime props specification used for validation/normalization
            self.props_spec = props
        if is_default and alias:
            raise ValueError(
                "A default import cannot have an alias (it uses the tag as the name)."
            )

        self.fn_signature = fn_signature
        COMPONENT_REGISTRY.get().add(self)

    def __repr__(self) -> str:
        alias_part = f", alias='{self.alias}'" if self.alias else ""
        default_part = ", default=True" if self.is_default else ""
        props_part = (
            f", props={self.props_spec!r}" if self.props_spec is not None else ""
        )
        return f"ReactComponent(tag='{self.tag}', import='{self.import_path}'{alias_part}{default_part}{props_part})"

    def __call__(self, *children: P.args, **props: P.kwargs) -> Node:
        key = props.pop("key", None)
        if key is not None and not isinstance(key, str):
            raise ValueError("key must be a string or None")
        real_props = cast(dict[str, Any], props)
        # Apply optional props specification: fill defaults, enforce required,
        # run serializers, and remap keys.
        if self.props_spec is not None:
            real_props = self.props_spec.apply(self.key, real_props)

        return Node(
            tag=f"$${self.key}",
            key=key,
            props=real_props,
            children=cast(tuple[NodeTree], children),
        )


def parse_fn_signature(fn: Callable[..., Any]) -> PropSpec:
    """Parse a function signature into a Props spec using a single pass.

    Rules:
    - May accept var-positional children `*children` (if annotated, must be NodeTree)
    - Must define `key: Optional[str] = None` (keyword-accepting)
    - Other props may be explicit keyword params and/or via **props: Unpack[TypedDict]
    - A prop may not be specified both explicitly and in the Unpack
    - Annotated[..., Prop(...)] on parameters is disallowed (use default Prop instead)
    """

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    explicit_props: dict[str, Prop] = {}
    explicit_spec: PropSpec
    unpack_spec: PropSpec

    var_positional: inspect.Parameter | None = None
    var_kw: inspect.Parameter | None = None
    key: inspect.Parameter | None = None

    # One pass: collect structure and build explicit spec as we go
    for p in params:
        # Disallow positional-only parameters
        if p.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise ValueError(
                "Function must not declare positional-only parameters besides *children",
            )

        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            var_positional = p
            continue

        if p.kind is inspect.Parameter.VAR_KEYWORD:
            var_kw = p
            continue

        if p.name == "key":
            key = p
            continue

        # For regular params, forbid additional required positionals
        if (
            p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            and p.default is inspect._empty
        ):
            raise ValueError(
                "Function signature must not declare additional required positional parameters; only *children is allowed for positionals",
            )

        if p.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        # Build explicit spec (skip 'key' handled above)
        annotation = p.annotation if p.annotation is not inspect._empty else Any
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
            if prop._type is MISSING:
                prop._type = runtime_type
        elif p.default is not inspect._empty:
            prop = Prop(default=p.default, _type=runtime_type)
        else:
            prop = Prop(_type=runtime_type)
        explicit_props[p.name] = prop

    explicit_spec = PropSpec(explicit_props, _skip_validation=True)

    # Validate *children annotation if present
    if var_positional is not None:
        annotation = var_positional.annotation
        if annotation is not inspect._empty and annotation is not NodeTree:
            raise TypeError(
                f"*{var_positional.name} must be annotated as `*{var_positional}: NodeTree`"
            )

    # Validate `key`` argument
    if key is None:
        raise ValueError("Function must define a `key: str | None = None` parameter")
    if key.default is not None:
        raise ValueError("'key' parameter must default to None")
    if key.kind not in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise ValueError("'key' parameter must be a keyword argument")

    # Parse **props as Unpack[TypedDict]
    unpack_spec = parse_typed_dict_props(var_kw)

    return unpack_spec.merge(explicit_spec)


class ComponentRegistry:
    """A registry for React components that can be used as a context manager."""

    def __init__(self):
        self._components: dict[str, ReactComponent] = {}
        self._token = None

    def add(self, component: ReactComponent):
        """Adds a component to the registry."""
        if component.key in self._components:
            raise ValueError(
                f"Duplicate component key '{component.key}' (existing: {self._components[component.key]!r}, new: {component!r})"
            )
        self._components[component.key] = component

    def clear(self):
        self._components.clear()

    def remove(self, key: str):
        """Removes a component from the registry by its key."""
        if key in self._components:
            del self._components[key]

    def get(self, key: str):
        """Gets a component from the registry by its key."""
        return self._components.get(key)

    def items(self):
        """Returns a copy of the components as a dictionary."""
        return self._components.copy()

    def list(self):
        return list(self._components.values())

    def __enter__(self) -> "ComponentRegistry":
        self._token = COMPONENT_REGISTRY.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            COMPONENT_REGISTRY.reset(self._token)
            self._token = None


COMPONENT_REGISTRY: ContextVar[ComponentRegistry] = ContextVar(
    "component_registry", default=ComponentRegistry()
)


def registered_react_components():
    """Get all registered React components."""
    return COMPONENT_REGISTRY.get().list()


# ----------------------------------------------------------------------------
# Utilities: Build Props specs from TypedDict definitions
# ----------------------------------------------------------------------------


def _is_typeddict_type(cls: type) -> bool:
    """Best-effort detection for TypedDict types across Python versions."""
    return isinstance(getattr(cls, "__annotations__", None), dict) and getattr(
        cls, "__total__", None
    ) in (True, False)


def _unwrap_required_notrequired(annotation: Any) -> tuple[Any, Optional[bool]]:
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

    # Optional[T] / Union[...]
    if origin in (Union, UnionType) or (
        origin is None and getattr(annotation, "__origin__", None) is Union
    ):
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
        literal_types = {type(v) for v in args}
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


def _extract_prop_from_annotated(annotation: Any) -> tuple[Any, Optional[Prop[Any]]]:
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


def parse_typed_dict_props(var_kw: inspect.Parameter | None) -> PropSpec:
    """
    Build a Props spec from a TypedDict class.

    - Required vs optional is inferred from __required_keys__/__optional_keys__ when
      available, otherwise from Required/NotRequired wrappers or the class __total__.
    - Types are converted to runtime-checkable types for isinstance checks.
    """
    # No **props -> no keyword arguments defined here
    if not var_kw:
        return PropSpec({})

    # Untyped **props -> allow all
    annot = var_kw.annotation
    if annot in (None, inspect._empty):
        return PropSpec({}, allow_unspecified=True)

    # From here, we should have **props: Unpack[MyProps] where MyProps is a TypedDict
    origin = get_origin(annot)
    if origin is not Unpack:
        raise TypeError(
            "**props must be annotated as typing.Unpack[Props] where Props is a TypedDict"
        )
    unpack_args = get_args(annot)
    if not unpack_args:
        raise TypeError("Unpack must wrap a TypedDict class, e.g., Unpack[MyProps]")
    typed_dict_cls = unpack_args[0]

    if not isinstance(typed_dict_cls, type) and _is_typeddict_type(typed_dict_cls):
        raise TypeError("Unpack must wrap a TypedDict class, e.g., Unpack[MyProps]")

    annotations: dict[str, Any] = getattr(typed_dict_cls, "__annotations__", {})
    required_keys: set[str] | None = getattr(typed_dict_cls, "__required_keys__", None)
    total_default: bool = bool(getattr(typed_dict_cls, "__total__", True))

    spec: dict[str, type | Prop] = {}

    for key, annotation in annotations.items():
        # First see if runtime provides explicit required/optional sets
        annotation, annotation_required = _unwrap_required_notrequired(annotation)
        # Extract Prop metadata from Annotated if present
        annotation, annotation_prop = _extract_prop_from_annotated(annotation)
        if required_keys is not None:
            required = key in required_keys
        else:
            required = annotation_required

        runtime_type = _annotation_to_runtime_type(annotation)

        if is_required:
            # Keep minimal form unless we need tuple types
            if isinstance(runtime_type, tuple):
                spec[key] = Prop(runtime_type)  # type: ignore[arg-type]
            else:
                spec[key] = runtime_type  # type: ignore[assignment]
        else:
            spec[key] = Prop(runtime_type, required=False)  # type: ignore[arg-type]

    # We choose total=True since we marked optional fields ourselves
    return PropSpec(spec, total=True)


# ----------------------------------------------------------------------------
# Public decorator: define a wrapped React component from a Python function
# ----------------------------------------------------------------------------


def react_component(
    *,
    tag: str | Literal["default"],
    import_: str,
    alias: str | None = None,
    is_default: bool = False,
) -> Callable[[Callable[P, NodeTree]], ReactComponent[P]]:
    """
    Decorator to define a React component wrapper. The decorated function is
    passed to `ReactComponent`, which parses and validates its signature.
    """

    def decorator(fn: Callable[P, NodeTree]) -> ReactComponent[P]:
        return ReactComponent(
            tag=tag,
            import_path=import_,
            alias=alias,
            is_default=bool(is_default),
            fn_signature=fn,
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
