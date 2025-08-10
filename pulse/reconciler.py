from contextvars import ContextVar
from dataclasses import dataclass
from re import sub
from typing import Callable
from pulse.diff import (
    InsertOperation,
    ReplaceOperation,
    UpdatePropsOperation,
    VDOMOperation,
)
from pulse.reactive import Effect
from pulse.hooks import HookState
from pulse.vdom import (
    VDOM,
    Callbacks,
    Component,
    ComponentNode,
    Node,
    NodeTree,
    Props,
    VDOMNode,
)


@dataclass
class RenderResult:
    render_count: int
    vdom: NodeTree
    ops: list[VDOMOperation]
    callbacks: Callbacks


class RenderRoot:
    vdom: NodeTree
    # global for now, will have separate effets per render node down the line
    effect: Effect | None

    render_nodes: dict[str, "RenderNode"]

    resolver: "Resolver"
    render_count: int

    def __init__(self, fn: Callable[[], NodeTree], vdom: VDOM) -> None:
        self.render_nodes = {"": RenderNode(fn)}
        self.vdom = Node.from_vdom(vdom)
        self.callbacks = {}
        self.effect = None
        self.render_count = 0
        pass

    # WIP! Not implemented yet
    def render(self) -> RenderResult:
        self.render_count += 1
        new_tree = self.render_tree.render()
        new_tree = Resolver(self.render_nodes).run(
            render_tree=self.render_tree, old_tree=self.vdom, new_tree=new_tree
        )
        self.vdom = new_tree
        return RenderResult(
            render_count=self.render_count,
            vdom=new_tree,
            callbacks=self.resolver.callbacks,
            ops=self.resolver.operations,
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
        with self.hooks.mount():
            self.last_render = self.fn(*args, **kwargs)
        return self.last_render


RENDER_CTX: ContextVar[RenderNode | None] = ContextVar(
    "pulse_render_context", default=None
)


class Resolver:
    def __init__(self) -> None:
        self.callbacks: Callbacks = {}
        self.operations: list[VDOMOperation] = []

    # WIP, not implemented yet!
    def resolve_node(
        self,
        render_tree: RenderNode,
        old_tree: NodeTree,
        new_tree: NodeTree,
        path="",
    ) -> VDOM:
        if not same_node(old_tree, new_tree):
            new_subtree = self._render_subtree(
                render_tree=render_tree, tree=new_tree, path=path
            )
            if isinstance(new_subtree, Node):
                new_subtree = new_subtree._render_node(path, self.callbacks)
            if old_tree is None:
                self.operations.append(
                    InsertOperation(type="insert", path=path, data=new_subtree)
                )
            else:
                self.operations.append(
                    ReplaceOperation(type="replace", path=path, data=new_subtree)
                )
            return new_subtree

        # At this point, we are dealing with the same node. We need to diff its props + its children
        if isinstance(old_tree, Node):
            assert isinstance(new_tree, Node)
            if old_tree.props != new_tree.props:
                if new_tree.props:
                    new_props = self._capture_callbacks(new_tree.props, path=path)
                else:
                    new_props = {}
                self.operations.append(
                    UpdatePropsOperation(type="update_props", path=path, data=new_props)
                )

            # TODO: diff children

        if isinstance(old_tree, ComponentNode):
            assert (
                isinstance(new_tree, ComponentNode)
                and old_tree.fn == new_tree.fn
                and old_tree.key == new_tree.key
            )
            child_node = render_tree.children[path]
            child_tree = child_node.render(*new_tree.args, **new_tree.kwargs)

    def render_tree(self, render_parent: RenderNode, node: NodeTree, path: str) -> VDOM:
        if isinstance(node, ComponentNode):
            # If we're here, this is a new component
            render_node = RenderNode(fn=node.fn)
            subtree = render_node.render(*node.args, **node.kwargs)
            print("Rendered component, subtree=",subtree)
            render_parent.children[path] = render_node
            return self.render_tree(render_parent=render_node, node=subtree, path=path)

        elif isinstance(node, Node):
            vdom_node: VDOMNode = {"tag": node.tag}
            print("Rendering node:", node)
            if node.key:
                vdom_node["key"] = node.key
            if node.props:
                vdom_node["props"] = self._capture_callbacks(node.props, path=path)
            if node.children:
                path_prefix = path + "." if path else path
                vdom_node["children"] = [
                    self.render_tree(
                        render_parent=render_parent,
                        node=child,
                        path=f"{path_prefix}{i}",
                    )
                    for i, child in enumerate(node.children)
                ]
            return vdom_node
        else:
            return node

    def _capture_callbacks(self, props: Props, path: str):
        if not any(callable(v) for v in props.values()):
            print('no callables')
            return props

        path_prefix = (path + ".") if path else ""
        updated_props = props.copy()
        for k, v in props.items():
            if callable(v):
                callback_key = f"{path_prefix}{k}"
                updated_props[k] = f"$$fn:{callback_key}"
                self.callbacks[callback_key] = v
        print('updated props:', updated_props)
        return updated_props


def same_node(left: NodeTree, right: NodeTree):
    # Handles primitive equality
    if left == right:
        return True

    if isinstance(left, Node) and isinstance(right, Node):
        return left.tag == right.tag
    if isinstance(left, ComponentNode) and isinstance(right, ComponentNode):
        # Components preserve state if they use the same function + they are
        # both unkeyed OR both with the same key
        return left.fn == right.fn and left.key == right.key

    return False
