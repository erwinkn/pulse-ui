"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

from __future__ import annotations
import functools
from types import NoneType
from collections.abc import Iterable as _Iterable
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


# ============================================================================
# Core VDOM
# ============================================================================

PrimitiveNode = Union[str, int, float, None]
NodeTree = Union["Node", "ComponentNode", PrimitiveNode]
# A child can be a NodeTree or any iterable yielding children (e.g., generators)
Child = Union[NodeTree, _Iterable[NodeTree]]
Children = Sequence[Child]

P = ParamSpec("P")


class VDOMNode(TypedDict):
    tag: str
    key: NotRequired[str]
    props: NotRequired[dict[str, Any]]  # does not include callbacks
    children: "NotRequired[Sequence[VDOMNode | PrimitiveNode] | None]"
    # Optional flag to indicate the element should be lazily loaded on the client
    lazy: NotRequired[bool]


class Callback(NamedTuple):
    fn: Callable
    n_args: int


def NOOP(*_args):
    return None


Callbacks = dict[str, Callback]
VDOM = Union[VDOMNode, PrimitiveNode]
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
        *,
        lazy: bool | None = None,
    ):
        self.tag = tag
        # Normalize to None
        self.props = props or None
        self.children = children or None
        self.allow_children = allow_children
        self.key = key or None
        self.lazy = lazy or None
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
        vdom: VDOM, callbacks: Optional[Callbacks] = None
    ) -> Union["Node", PrimitiveNode]:
        """Create a Node tree from a VDOM structure.

        - Primitive values are returned as-is
        - Callback placeholders (values starting with "$$fn:") are stripped
          from props since we cannot reconstruct Python callables here
        """

        if isinstance(vdom, (str, int, float, bool, NoneType)):
            return vdom

        tag = cast(str, vdom.get("tag"))
        props = cast(dict[str, Any] | None, vdom.get("props")) or {}
        key_value = cast(Optional[str], vdom.get("key"))

        callbacks = callbacks or {}
        copied = False
        for k, v in props.items():
            if isinstance(v, str) and v.startswith("$$fn:"):
                callback_id = v[len("$$fn:") :]
                callback = callbacks.get(callback_id)
                if not callback:
                    raise ValueError(f"Missing callback '{callback_id}'")
                if not copied:
                    props = props.copy()
                    copied = True
                props[k] = callback.fn

        children_value: list[NodeTree] | None = None
        raw_children = cast(
            Sequence[VDOMNode | PrimitiveNode] | None, vdom.get("children")
        )
        if raw_children is not None:
            children_value = []
            for raw_child in raw_children:
                children_value.append(Node.from_vdom(raw_child, callbacks=callbacks))

        return Node(
            tag=tag,
            props=props or None,
            children=children_value,
            key=key_value,
        )


# ============================================================================
# Tag Definition Functions
# ============================================================================


# ----------------------------------------------------------------------------
# Formatting helpers (internal)
# ----------------------------------------------------------------------------


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


def _pretty_repr(node: NodeTree):
    if isinstance(node, Node):
        return f"<{node.tag}>"
    if isinstance(node, ComponentNode):
        return f"<{node.name}"
    return repr(node)


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
        if isinstance(child, _Iterable) and not isinstance(child, str):
            child = list(child)
            n_items = min(len(child), max_items - len(out))
            out.extend(_pretty_repr(c) for c in child[:n_items])
        else:
            out.append(_pretty_repr(child))
    if len(children) > (max_items - 1):
        out.append(f"…(+{len(children) - (max_items - 1)})")
    return out


# --- Components ---


class Component(Generic[P]):
    def __init__(self, fn: Callable[P, NodeTree], name: Optional[str] = None) -> None:
        self.fn = fn
        self.name = name or _infer_component_name(fn)

    def __call__(
        self, key: Optional[str] = None, *args: P.args, **kwargs: P.kwargs
    ) -> "ComponentNode":
        return ComponentNode(
            fn=self.fn, key=key, args=args, kwargs=kwargs, name=self.name
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
    ) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.key = key
        self.name = name or _infer_component_name(fn)

    def __getitem__(self, children_arg: Union[Child, tuple[Child, ...]]):
        if "children" in self.kwargs and self.kwargs.get("children"):
            raise ValueError(
                f"Component {self.name} already has children: {self.kwargs.get('children')}"
            )
        kwargs = self.kwargs.copy()
        if isinstance(children_arg, tuple):
            new_children = cast(list[Child], list(children_arg))
        else:
            new_children = [children_arg]
        kwargs["children"] = new_children
        result = ComponentNode(
            fn=self.fn,
            args=self.args,
            kwargs=kwargs,
            name=self.name,
        )
        return result

    def __repr__(self) -> str:
        return (
            f"ComponentNode(name={self.name!r}, key={self.key!r}, "
            f"args={_short_args(self.args)}, kwargs={_short_props(self.kwargs)})"
        )


@overload
def component(fn: Callable[P, NodeTree]) -> Component[P]: ...
@overload
def component(
    fn: None = None, *, name: Optional[str] = None
) -> Callable[[Callable[P, NodeTree]], Component[P]]: ...


# The explicit return type is necessary for the type checker to be happy
def component(
    fn: Callable[P, NodeTree] | None = None, *, name: str | None = None
) -> Component[P] | Callable[[Callable[P, NodeTree]], Component[P]]:
    def decorator(fn: Callable[P, NodeTree]):
        return Component(fn, name)

    if fn is not None:
        return decorator(fn)
    return decorator


# ----------------------------------------------------------------------------
# Component naming heuristics
# ----------------------------------------------------------------------------


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
