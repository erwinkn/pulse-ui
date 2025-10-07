"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

from __future__ import annotations
import functools
import warnings
from types import NoneType
from inspect import signature, Parameter
from collections.abc import Iterable
from typing import (
    Any,
    NamedTuple,
    NotRequired,
    Optional,
    Callable,
    Sequence,
    TypedDict,
    Union,
    cast,
    Generic,
    ParamSpec,
    overload,
)

from pulse.hooks.core import HookContext


# ============================================================================
# Core VDOM
# ============================================================================

Primitive = Union[str, int, float, None]
Element = Union["Node", "ComponentNode", Primitive]
# A child can be an Element or any iterable yielding children (e.g., generators)
Child = Union[Element, Iterable[Element]]
Children = Sequence[Child]

P = ParamSpec("P")


class VDOMNode(TypedDict):
    tag: str
    key: NotRequired[str]
    props: NotRequired[dict[str, Any]]  # does not include callbacks
    children: "NotRequired[Sequence[VDOMNode | Primitive] | None]"


class Callback(NamedTuple):
    fn: Callable
    n_args: int


def NOOP(*_args):
    return None


Callbacks = dict[str, Callback]
VDOM = Union[VDOMNode, Primitive]
Props = dict[str, Any]


class Node:
    """
    A UI tree node that matches the TypeScript UIElementNode format.
    This directly generates the structure expected by the React frontend.
    """

    def __init__(
        self,
        tag: str,
        props: Optional[dict[str, Any] | None] = None,
        children: Optional[Children] = None,
        key: Optional[str] = None,
        allow_children=True,
    ):
        self.tag = tag
        # Normalize to None
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
            raise ValueError(f"{self.tag} cannot have children")

    # --- Pretty printing helpers -------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        return (
            f"Node(tag={self.tag!r}, key={self.key!r}, props={_short_props(self.props)}, "
            f"children={_short_children(self.children)})"
        )

    def __getitem__(
        self,
        children_arg: Union[Child, tuple[Child, ...]],
    ):
        """Support indexing syntax: div()[children] or div()["text"]

        Children may include iterables (lists, generators) of nodes, which will
        be flattened during render.
        """
        if self.children:
            raise ValueError(f"Node already has children: {self.children}")

        if isinstance(children_arg, tuple):
            new_children = cast(list[Child], list(children_arg))
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
        vdom: VDOM,
        callbacks: Optional[Callbacks] = None,
        *,
        path: str = "",
    ) -> Union["Node", Primitive]:
        """Create a Node tree from a VDOM structure.

        - Primitive values are returned as-is
        - Callbacks can be reattached by providing both `callbacks` (the
          callable registry) and `callback_props` (props per VDOM path)
        """

        if isinstance(vdom, (str, int, float, bool, NoneType)):
            return vdom

        tag = cast(str, vdom.get("tag"))
        props = cast(dict[str, Any] | None, vdom.get("props")) or {}
        key_value = cast(Optional[str], vdom.get("key"))

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
        raw_children = cast(Sequence[VDOMNode | Primitive] | None, vdom.get("children"))
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


class Component(Generic[P]):
    def __init__(self, fn: Callable[P, Element], name: Optional[str] = None) -> None:
        self.fn = fn
        self.name = name or _infer_component_name(fn)
        self._takes_children = _takes_children(fn)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> "ComponentNode":
        key = kwargs.get("key")
        if key is not None and not isinstance(key, str):
            raise ValueError("key must be a string or None")

        return ComponentNode(
            fn=self.fn,
            key=key,
            args=args,
            kwargs=kwargs,
            name=self.name,
            takes_children=self._takes_children,
        )

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        return f"Component(name={self.name!r}, fn={_callable_qualname(self.fn)!r})"

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        return self.name


class ComponentNode:
    def __init__(
        self,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        name: Optional[str] = None,
        key: Optional[str] = None,
        takes_children: bool = True,
    ) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.key = key
        self.name = name or _infer_component_name(fn)
        self.takes_children = takes_children
        # Used for rendering
        self.contents: Element | None = None
        self.hooks = HookContext()

    def __getitem__(self, children_arg: Union[Child, tuple[Child, ...]]):
        if not self.takes_children:
            raise TypeError(
                (
                    f"Component {self.name} does not accept children. "
                    "Update the component signature to include '*children' to allow children."
                )
            )
        if self.args:
            raise ValueError(
                f"Component {self.name} already received positional arguments. Pass all arguments as keyword arguments in order to pass children using brackets."
            )
        if not isinstance(children_arg, tuple):
            children_arg = (children_arg,)
        # Flatten children for ComponentNode as well
        flattened_children = _flatten_children(
            children_arg, parent_name=f"<{self.name}>"
        )
        result = ComponentNode(
            fn=self.fn,
            args=tuple(flattened_children),
            kwargs=self.kwargs,
            name=self.name,
            key=self.key,
            takes_children=self.takes_children,
        )
        return result

    def __repr__(self) -> str:
        return (
            f"ComponentNode(name={self.name!r}, key={self.key!r}, "
            f"args={_short_args(self.args)}, kwargs={_short_props(self.kwargs)})"
        )


@overload
def component(fn: Callable[P, Element]) -> Component[P]: ...
@overload
def component(
    fn: None = None, *, name: Optional[str] = None
) -> Callable[[Callable[P, Element]], Component[P]]: ...


# The explicit return type is necessary for the type checker to be happy
def component(
    fn: Callable[P, Element] | None = None, *, name: str | None = None
) -> Component[P] | Callable[[Callable[P, Element]], Component[P]]:
    def decorator(fn: Callable[P, Element]):
        return Component(fn, name)

    if fn is not None:
        return decorator(fn)
    return decorator


# ----------------------------------------------------------------------------
# Component naming heuristics
# ----------------------------------------------------------------------------


def _flatten_children(children: Children, *, parent_name: str) -> Sequence[Element]:
    """Flatten children and emit warnings for unkeyed iterables."""
    flat: list[Element] = []
    return_tuple = isinstance(children, tuple)

    def visit(item: Child) -> None:
        if isinstance(item, Iterable) and not isinstance(item, str):
            # If any Node/ComponentNode yielded by this iterable lacks a key,
            # emit a single warning for this iterable.
            missing_key = False
            for sub in item:
                if isinstance(sub, (Node, ComponentNode)) and sub.key is None:
                    missing_key = True
                visit(sub)
            if missing_key:
                # Warn once per iterable without keys on its elements
                warnings.warn(
                    (
                        "[Pulse] Iterable children of {} contain elements without 'key'. "
                        "Add a stable 'key' to each element inside iterables to improve reconciliation."
                    ).format(parent_name),
                    stacklevel=3,
                )
        else:
            # Not an iterable child: must be a Element or primitive
            flat.append(item)

    for child in children:
        visit(child)

    seen_keys: set[str] = set()
    for child in flat:
        if isinstance(child, (Node, ComponentNode)) and child.key is not None:
            if child.key in seen_keys:
                raise ValueError(
                    (
                        f"[Pulse] Duplicate key '{child.key}' found among children of {parent_name}. "
                        "Keys must be unique per sibling set."
                    )
                )
            seen_keys.add(child.key)

    return tuple(flat) if return_tuple else flat


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


def _takes_children(fn: Callable[..., Any]) -> bool:
    # Lightweight check: children allowed if function accepts positional
    # arguments
    try:
        sig = signature(fn)
    except (ValueError, TypeError):
        # Builtins or callables without inspectable signature: assume no children
        return False
    for p in sig.parameters.values():
        if p.kind in (
            Parameter.VAR_POSITIONAL,
            Parameter.POSITIONAL_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return True
    return False


# ----------------------------------------------------------------------------
# Formatting helpers (internal)
# ----------------------------------------------------------------------------


def _pretty_repr(node: Element):
    if isinstance(node, Node):
        return f"<{node.tag}>"
    if isinstance(node, ComponentNode):
        return f"<{node.name}"
    return repr(node)


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
