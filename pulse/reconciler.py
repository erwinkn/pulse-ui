from contextvars import ContextVar
from dataclasses import dataclass
import inspect
from typing import Callable, Sequence
from pulse.diff import (
    InsertOperation,
    RemoveOperation,
    ReplaceOperation,
    UpdatePropsOperation,
    VDOMOperation,
)
from pulse.reactive import Effect
from pulse.hooks import HookState
from pulse.vdom import (
    VDOM,
    Callback,
    Callbacks,
    ComponentNode,
    Node,
    NodeTree,
    Props,
    VDOMNode,
)


@dataclass
class RenderResult:
    render_count: int
    ops: list[VDOMOperation]
    callbacks: Callbacks


class RenderRoot:
    # global for now, will have separate effets per render node down the line
    effect: Effect | None
    render_tree: "RenderNode"
    render_count: int

    def __init__(self, fn: Callable[[], NodeTree]) -> None:
        self.render_tree = RenderNode(fn)
        self.callbacks = {}
        self.effect = None
        self.render_count = 0
        pass

    def render(self) -> RenderResult:
        self.render_count += 1
        resolver = Resolver()
        last_render = self.render_tree.last_render
        new_tree = self.render_tree.render()
        resolver.reconcile_node(
            render_parent=self.render_tree, old_tree=last_render, new_tree=new_tree
        )
        return RenderResult(
            render_count=self.render_count,
            callbacks=resolver.callbacks,
            ops=resolver.operations,
        )


class RenderNode:
    fn: Callable[..., NodeTree]
    hooks: HookState
    last_render: NodeTree
    children: dict[str, "RenderNode"]

    def __init__(self, fn: Callable[..., NodeTree]) -> None:
        self.fn = fn
        self.hooks = HookState()
        self.last_render = None
        self.children = {}

    def render(self, *args, **kwargs) -> NodeTree:
        with self.hooks.ctx():
            self.last_render = self.fn(*args, **kwargs)

        return self.last_render

    def unmount(self):
        self.hooks.unmount()


RENDER_CTX: ContextVar[RenderNode | None] = ContextVar(
    "pulse_render_context", default=None
)


class Resolver:
    def __init__(self) -> None:
        self.callbacks: Callbacks = {}
        self.operations: list[VDOMOperation] = []

    def reconcile_node(
        self,
        render_parent: RenderNode,
        old_tree: NodeTree,
        new_tree: NodeTree,
        path="",
    ) -> NodeTree:
        print(f"Reconciling {old_tree} vs. {new_tree}")
        if not same_node(old_tree, new_tree):
            print("Nodes are different")
            # If we're replacing a ComponentNode, unmount the old one before rendering the new
            if isinstance(old_tree, ComponentNode):
                render_parent.children[path].unmount()
            new_vdom, normalized = self.render_tree(
                render_parent=render_parent, node=new_tree, path=path
            )
            if old_tree is None:
                self.operations.append(
                    InsertOperation(type="insert", path=path, data=new_vdom)
                )
            elif new_tree is None:
                self.operations.append(RemoveOperation(type="remove", path=path))
            else:
                self.operations.append(
                    ReplaceOperation(type="replace", path=path, data=new_vdom)
                )
            return normalized

        # At this point, we are dealing with the same node. We need to diff its props + its children
        if isinstance(old_tree, Node):
            assert isinstance(new_tree, Node)
            # We want to capture callbacks regardless, in case the function references have changed
            new_props = (
                self._capture_callbacks(new_tree.props, path=path)
                if new_tree.props
                else None
            )
            # TODO: old_tree
            if old_tree.props != new_props:
                print(f"-> props difference = {old_tree.props} vs {new_props}")
                self.operations.append(
                    UpdatePropsOperation(
                        type="update_props", path=path, data=new_props or {}
                    )
                )
            normalized_children: list[NodeTree] = []
            if old_tree.children or new_tree.children:
                normalized_children = self.reconcile_children(
                    render_parent=render_parent,
                    path=path,
                    old_children=old_tree.children or [],
                    new_children=new_tree.children or [],
                )
            return Node(
                tag=new_tree.tag,
                props=new_props or None,
                children=normalized_children or None,
                key=new_tree.key,
            )

        if isinstance(old_tree, ComponentNode):
            assert (
                isinstance(new_tree, ComponentNode)
                and old_tree.fn == new_tree.fn
                and old_tree.key == new_tree.key
            )
            render_child = render_parent.children[path]
            last_render = render_child.last_render
            new_render = render_child.render(*new_tree.args, **new_tree.kwargs)
            normalized = self.reconcile_node(
                render_parent=render_child,
                old_tree=last_render,
                new_tree=new_render,
                path=path,
            )
            render_child.last_render = normalized
            # Preserve component placeholder in normalized tree
            return new_tree

        # Default: primitives or unchanged nodes
        return new_tree

    def reconcile_children(
        self,
        render_parent: RenderNode,
        path: str,
        old_children: Sequence[NodeTree],
        new_children: Sequence[NodeTree],
    ) -> list[NodeTree]:
        print(f"[reconcile_children] {old_children} vs. {new_children}")
        path_prefix = path + "." if len(path) > 0 else path
        # - hasattr/getattr avoids isinstance checks.
        # - (TODO: benchmark whether this is better).
        # - We store the current position of the keyed elements to make it easy
        #   to retrieve RenderNodes and build move operations.
        by_key_old: dict[str, tuple[int, NodeTree]] = {}
        by_key_new: dict[str, tuple[int, NodeTree]] = {}
        for i, node in enumerate(old_children):
            if key := getattr(node, "key", None):
                by_key_old[key] = (i, node)
        for i, node in enumerate(new_children):
            if key := getattr(node, "key", None):
                by_key_new[key] = (i, node)
        print(f"[reconcile_children] by_key_old = {by_key_old}")
        print(f"[reconcile_children] by_key_new = {by_key_new}")

        if len(by_key_old) > 0 or len(by_key_new) > 0:
            # keyed reconciliation first
            raise NotImplementedError()

        else:
            N_shared = min(len(old_children), len(new_children))
            normalized_children: list[NodeTree] = []
            for i in range(N_shared):
                child_norm = self.reconcile_node(
                    render_parent=render_parent,
                    path=f"{path_prefix}{i}",
                    old_tree=old_children[i],
                    new_tree=new_children[i],
                )
                normalized_children.append(child_norm)

            # Only runs if there are more old nodes than new ones
            for i in range(N_shared, len(old_children)):
                child_path = f"{path_prefix}{i}"
                if isinstance(old_children[i], ComponentNode):
                    # TODO in tests: verify that components are unmounted correctly
                    render_parent.children[child_path].unmount()
                self.operations.append(
                    RemoveOperation(type="remove", path=f"{path_prefix}{i}")
                )

            # Only runs if there are more new nodes than old ones
            for i in range(N_shared, len(new_children)):
                child_path = f"{path_prefix}{i}"
                new_node = new_children[i]
                new_vdom, norm_child = self.render_tree(
                    render_parent=render_parent, node=new_node, path=child_path
                )
                self.operations.append(
                    InsertOperation(type="insert", path=child_path, data=new_vdom)
                )
                normalized_children.append(norm_child)

            return normalized_children

    def render_tree(
        self, render_parent: RenderNode, node: NodeTree, path: str
    ) -> tuple[VDOM, NodeTree]:
        if isinstance(node, ComponentNode):
            # If we're here, this is a new component
            render_node = RenderNode(fn=node.fn)
            subtree = render_node.render(*node.args, **node.kwargs)
            render_parent.children[path] = render_node
            vdom, normalized = self.render_tree(
                render_parent=render_node, path=path, node=subtree
            )
            render_node.last_render = normalized
            # Preserve ComponentNode in normalized tree
            return vdom, node

        elif isinstance(node, Node):
            vdom_node: VDOMNode = {"tag": node.tag}
            if node.key:
                vdom_node["key"] = node.key
            if node.props:
                vdom_node["props"] = (
                    self._capture_callbacks(node.props, path=path) or {}
                )
            normalized_children: list[NodeTree] | None = None
            if node.children:
                path_prefix = path + "." if path else path
                v_children: list[VDOM] = []
                normalized_children = []
                for i, child in enumerate(node.children):
                    v, norm = self.render_tree(
                        render_parent=render_parent,
                        path=f"{path_prefix}{i}",
                        node=child,
                    )
                    v_children.append(v)
                    normalized_children.append(norm)
                vdom_node["children"] = v_children
            normalized_node = Node(
                tag=node.tag,
                props=vdom_node.get("props") or None,
                children=normalized_children or None,
                key=node.key,
            )
            return vdom_node, normalized_node
        else:
            return node, node

    def _capture_callbacks(self, props: Props, path: str) -> Props:
        if not any(callable(v) for v in props.values()):
            return props

        path_prefix = (path + ".") if path else ""
        updated_props = props.copy()
        for k, v in props.items():
            if callable(v):
                callback_key = f"{path_prefix}{k}"
                updated_props[k] = f"$$fn:{callback_key}"
                self.callbacks[callback_key] = Callback(
                    fn=v, n_args=len(inspect.signature(v).parameters)
                )
        return updated_props


def same_node(left: NodeTree, right: NodeTree):
    # Handles primitive equality
    if left == right:
        return True

    if isinstance(left, Node) and isinstance(right, Node):
        return left.tag == right.tag and left.key == right.key
    if isinstance(left, ComponentNode) and isinstance(right, ComponentNode):
        # Components preserve state if they use the same function + they are
        # both unkeyed OR both with the same key
        return left.fn == right.fn and left.key == right.key

    return False
