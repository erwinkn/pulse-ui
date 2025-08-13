# ============================================================================
# React Component Integration
# ============================================================================

import inspect
from contextvars import ContextVar
from typing import Any, Callable, Generic, Literal, Optional, ParamSpec, TypeVar, cast

from pulse.vdom import Node, NodeTree


T = TypeVar("T")


class Prop(Generic[T]):
    def __init__(
        self,
        type_: type[T],
        default: Optional[T] = None,
        required: Optional[bool] = None,
        default_factory: Optional[Callable[[], T]] = None,
        serialize: Optional[Callable[[T], Any]] = None,
    ) -> None:
        self.type_ = type_
        self.default = default
        self.required = required
        self.default_factory = default_factory
        self.serialize = serialize


class Props:
    def __init__(self, spec: dict[str, type | Prop], total=True) -> None:
        self.spec = spec
        # Specifies whether props are required or optional by default
        self.total = total


P = ParamSpec("P")


def default_hint(
    *children: NodeTree, key: Optional[str] = None, **props
) -> NodeTree: ...
def default_hint_without_children(key: Optional[str] = None, **props) -> NodeTree: ...


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
        default_props: Optional[dict] = None,
        props: Optional[Props] = None,
        hint: Callable[P, NodeTree] = default_hint,
    ):
        self.tag = tag
        self.key = alias or tag
        self.import_path = import_path
        self.alias = alias
        self.default_props = default_props
        self.is_default = is_default
        # Optional runtime props specification used for validation/normalization
        self.props_spec = props
        if is_default and alias:
            raise ValueError(
                "A default import cannot have an alias (it uses the tag as the name)."
            )

        if hint not in (default_hint, default_hint_without_children):
            _validate_hint_signature(hint)
        self.hint = hint
        COMPONENT_REGISTRY.get().add(self)

    def __call__(self, *children: P.args, **props: P.kwargs) -> Node:
        # Merge defaults from constructor with call-time props (call-time wins)
        if self.default_props:
            props.update(self.default_props)

        # Apply optional props specification: fill defaults, enforce required,
        # run serializers, and pass through unknown keys unchanged
        if self.props_spec is not None:
            self._apply_props_spec(props)
        key = props.pop("key", None)
        if key is not None and not isinstance(key, str):
            raise ValueError("Key has to be a string or None.")

        return Node(
            tag=f"$${self.key}",
            key=key,
            props=props,
            children=cast(tuple[NodeTree], children),
        )

    def _apply_props_spec(self, props: dict):
        """
        Normalize props according to the attached Props spec:
        - For keys in spec:
          - If provided, optionally type-check and serialize
          - If missing, use default_factory/default or error if required
        - Keys not in spec are passed through unchanged
        """
        assert self.props_spec is not None

        # Start with passthrough for unknown keys; fill known keys below
        unknown_keys = [k for k in props.keys() if k not in self.props_spec.spec]
        if unknown_keys:
            raise ValueError(
                f"Unexpected prop(s) for {self.key}: {', '.join(repr(k) for k in unknown_keys)}"
            )

        for key, prop in self.props_spec.spec.items():
            # Resolve type-only entry to Prop
            if not isinstance(prop, Prop):
                prop = Prop(type_=prop)

            is_required = (
                prop.required
                if prop.required is not None
                else bool(self.props_spec.total)
            )

            if key in props:
                value = props[key]
            else:
                if prop.default_factory is not None:
                    value = prop.default_factory()
                elif prop.default is not None:
                    value = prop.default
                else:
                    if is_required:
                        raise ValueError(
                            f"Missing required prop '{key}' for {self.key}"
                        )
                    # Optional and no default: skip including key
                    continue

            # Best-effort runtime type check if expected_type is a class/tuple
            try:
                if isinstance(prop.type_, type) or isinstance(prop.type_, tuple):
                    if value is not None and not isinstance(value, prop.type_):
                        raise TypeError(
                            f"Invalid type for prop '{key}': got {type(value).__name__}, "
                            f"expected {getattr(prop.type_, '__name__', prop.type_)!r}"
                        )
            except TypeError:
                # expected_type is likely a typing construct not suitable for isinstance
                pass

            # Apply serializer if present
            if prop.serialize is not None:
                value = prop.serialize(value)

            props[key] = value


def _validate_hint_signature(hint: Callable[..., Any]) -> None:
    """
    Validate that a hint function conforms to Pulse's requirements:
    - Either no positional parameters, or a single variadic positional parameter
      (i.e., `*children`). If annotated, it must be `NodeTree`.
    - Must define an optional `key` parameter that defaults to None and is
      keyword-accepting (keyword-only or positional-or-keyword).
    Other keyword parameters (including **kwargs) are allowed.
    """

    sig = inspect.signature(hint)
    params = list(sig.parameters.values())

    var_positional_param: inspect.Parameter | None = None
    key_param: inspect.Parameter | None = None

    # Disallow positional-only params; they can't be passed via kwargs from Pulse
    for p in params:
        if p.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise ValueError("Hint must not declare positional-only parameters")

    for p in params:
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            if var_positional_param is not None:
                raise ValueError("Hint may not declare more than one *args parameter")
            var_positional_param = p
        elif p.name == "key":
            key_param = p

    # If a *children param exists, validate its annotation if provided
    if var_positional_param is not None:
        ann = var_positional_param.annotation
        if ann is not inspect._empty and ann is not NodeTree:
            raise TypeError("*children must be annotated as NodeTree if annotated")

    # Enforce the presence and shape of `key`
    if key_param is None:
        raise ValueError(
            "Hint must define an optional 'key' parameter with default None"
        )
    if key_param.default is not None:
        raise ValueError("Hint 'key' parameter must default to None")
    if key_param.kind not in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise ValueError(
            "Hint 'key' parameter must be keyword-accepting (keyword-only or positional-or-keyword)"
        )


class ComponentRegistry:
    """A registry for React components that can be used as a context manager."""

    def __init__(self):
        self._components: dict[str, ReactComponent] = {}
        self._token = None

    def add(self, component: ReactComponent):
        """Adds a component to the registry."""
        if component.key in self._components:
            raise ValueError(f"Duplicate component key {component.key}")
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
