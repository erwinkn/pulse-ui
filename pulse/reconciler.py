from contextvars import ContextVar
from dataclasses import dataclass
import inspect
from typing import Callable, Optional, Sequence
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
    tree: NodeTree
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
        new_tree = resolver.reconcile_node(
            render_parent=self.render_tree, old_tree=last_render, new_tree=new_tree
        )
        self.render_tree.last_render = new_tree
        return RenderResult(
            tree=new_tree,
            render_count=self.render_count,
            callbacks=resolver.callbacks,
            ops=resolver.operations,
        )


class RenderNode:
    fn: Callable[..., NodeTree]
    hooks: HookState
    last_render: NodeTree
    key: Optional[str]
    # Absolute position in the tree
    children: dict[str, "RenderNode"]

    def __init__(self, fn: Callable[..., NodeTree], key: Optional[str] = None) -> None:
        self.fn = fn
        self.hooks = HookState()
        self.last_render = None
        self.children = {}
        self.key = key

    def render(self, *args, **kwargs) -> NodeTree:
        # Render result needs to be normalized before reassigned to self.last_render
        with self.hooks.ctx():
            return self.fn(*args, **kwargs)

    def unmount(self):
        print(f"Unmounting RenderNode with key {self.key}")
        self.hooks.unmount()
        for child in self.children.values():
            child.unmount()


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
        relative_path="",
    ) -> NodeTree:
        if not same_node(old_tree, new_tree):
            # If we're replacing a ComponentNode, unmount the old one before
            # rendering the new.
            # NOTE: with our hack of only preserving component state during
            # keyed reconciliation, we will encounter scenarios where the render
            # node has already been moved here.
            print(f"Replacing {old_tree} with {new_tree}")
            if (
                isinstance(old_tree, ComponentNode)
                and relative_path in render_parent.children
            ):
                # HACK due to our general keyed reconciliation hack
                old_render_child = render_parent.children[relative_path]
                if old_render_child.key == old_tree.key:
                    print("Old child key:", old_render_child.key)
                    print("Old tree key:", old_tree.key)
                    render_parent.children.pop(relative_path).unmount()
            new_vdom, normalized = self.render_tree(
                render_parent=render_parent,
                node=new_tree,
                path=path,
                relative_path=relative_path,
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
                self.operations.append(
                    UpdatePropsOperation(
                        type="update_props", path=path, data=new_props or {}
                    )
                )
            normalized_children: list[NodeTree] = []
            if old_tree.children or new_tree.children:
                normalized_children = self.reconcile_children(
                    render_parent=render_parent,
                    old_children=old_tree.children or [],
                    new_children=new_tree.children or [],
                    path=path,
                    relative_path=relative_path,
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
            print("render parent children:", render_parent.children)
            render_child = render_parent.children[relative_path]
            last_render = render_child.last_render
            new_render = render_child.render(*new_tree.args, **new_tree.kwargs)
            normalized = self.reconcile_node(
                render_parent=render_child,
                old_tree=last_render,
                new_tree=new_render,
                path=path,
                # IMPORTANT: when recursing into a component's subtree, the
                # render nodes for its children are stored using paths
                # relative to that component. Reset the relative path here so
                # subsequent lookups match the keys used during render_tree.
                relative_path="",
            )
            render_child.last_render = normalized
            # Preserve component placeholder in normalized tree
            return new_tree

        # Default: primitives or unchanged nodes
        return new_tree

    def reconcile_children(
        self,
        render_parent: RenderNode,
        old_children: Sequence[NodeTree],
        new_children: Sequence[NodeTree],
        path: str,
        relative_path: str,
    ) -> list[NodeTree]:
        # - hasattr/getattr avoids isinstance checks.
        # - (TODO: benchmark whether this is better).
        # - We store the current position of the keyed elements to make it easy
        #   to retrieve RenderNodes and build move operations.
        keyed = any(getattr(node, "key", None) for node in old_children) or any(
            getattr(node, "key", None) for node in new_children
        )

        if keyed:
            return self.reconcile_children_keyed(
                render_parent=render_parent,
                old_children=old_children,
                new_children=new_children,
                path=path,
                relative_path=relative_path,
            )
        else:
            return self.reconcile_children_unkeyed(
                render_parent=render_parent,
                old_children=old_children,
                new_children=new_children,
                path=path,
                relative_path=relative_path,
            )

    def reconcile_children_keyed(
        self,
        render_parent: RenderNode,
        old_children: Sequence[NodeTree],
        new_children: Sequence[NodeTree],
        path: str,
        relative_path: str,
    ) -> list[NodeTree]:
        # HACK: only preserve component state and then perform an unkeyed
        # reconciliation. This is absolutely not optimal in terms of emitted
        # operations, but is very easy to implement.
        # TODO (future): study React's, Vue's, and morphdom's keyed
        # reconciliation algorithms to determine what we want to implement.
        old_keys: dict[str, int] = {}
        for old_idx, node in enumerate(old_children):
            # We only care about component state right now
            if not isinstance(node, ComponentNode):
                continue

            key: str | None = getattr(node, "key", None)
            if key:
                old_keys[key] = old_idx

        # Avoid overwriting children due to swaps. We first register all the
        # moves, then perform them.
        remap: dict[str, RenderNode] = {}
        for new_idx, node in enumerate(new_children):
            if not isinstance(node, ComponentNode):
                continue
            key: str | None = getattr(node, "key", None)
            if key in old_keys:
                old_idx = old_keys[key]
                if old_idx != new_idx:
                    old_path = join_path(relative_path, old_idx)
                    new_path = join_path(relative_path, new_idx)
                    remap[new_path] = render_parent.children.pop(old_path)
                    print(f"Moving {key} from {old_path} to {new_path}")
                    # Q: remove key from old node?
        render_parent.children.update(remap)

        return self.reconcile_children_unkeyed(
            render_parent=render_parent,
            old_children=old_children,
            new_children=new_children,
            path=path,
            relative_path=relative_path,
        )

    def reconcile_children_unkeyed(
        self,
        render_parent: RenderNode,
        old_children: Sequence[NodeTree],
        new_children: Sequence[NodeTree],
        path: str,
        relative_path: str,
    ) -> list[NodeTree]:
        N_shared = min(len(old_children), len(new_children))
        normalized_children: list[NodeTree] = []
        for i in range(N_shared):
            old_child = old_children[i]
            new_child = new_children[i]
            child_norm = self.reconcile_node(
                render_parent=render_parent,
                old_tree=old_child,
                new_tree=new_child,
                path=join_path(path, i),
                relative_path=join_path(relative_path, i),
            )
            normalized_children.append(child_norm)

        # Only runs if there are more old nodes than new ones
        for i in range(N_shared, len(old_children)):
            old_child = old_children[i]
            if isinstance(old_child, ComponentNode):
                # TODO in tests: verify that components are unmounted correctly
                old_render_node = render_parent.children[join_path(relative_path, i)]
                if old_render_node.key == old_child.key:
                    old_render_node.unmount()
            self.operations.append(
                RemoveOperation(type="remove", path=join_path(path, i))
            )

        # Only runs if there are more new nodes than old ones
        for i in range(N_shared, len(new_children)):
            new_node = new_children[i]
            new_vdom, norm_child = self.render_tree(
                render_parent=render_parent,
                node=new_node,
                path=join_path(path, i),
                relative_path=join_path(relative_path, i),
            )
            self.operations.append(
                InsertOperation(type="insert", path=join_path(path, i), data=new_vdom)
            )
            normalized_children.append(norm_child)

        return normalized_children

    def render_tree(
        self, render_parent: RenderNode, node: NodeTree, path: str, relative_path: str
    ) -> tuple[VDOM, NodeTree]:
        if isinstance(node, ComponentNode):
            print(
                f"Rendering {node} at path {path}, relative path {relative_path}. Render siblings: {render_parent.children}"
            )
            if relative_path in render_parent.children:
                render_node = render_parent.children[relative_path]
            else:
                render_node = RenderNode(fn=node.fn, key=node.key)
            subtree = render_node.render(*node.args, **node.kwargs)
            render_parent.children[relative_path] = render_node
            # Reset relative path
            vdom, normalized = self.render_tree(
                render_parent=render_node, path=path, relative_path="", node=subtree
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
                v_children: list[VDOM] = []
                normalized_children = []
                for i, child in enumerate(node.children):
                    v, norm = self.render_tree(
                        render_parent=render_parent,
                        path=join_path(path, i),
                        relative_path=join_path(relative_path, i),
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


# Longest increasing subsequence algorithm
def lis(seq: list[int]) -> list[int]:
    if not seq:
        return []
    # patience sorting style; store indices of seq
    tails: list[int] = []  # indices in seq forming tails
    prev: list[int] = [-1] * len(seq)
    for i, v in enumerate(seq):
        # binary search in tails on values of seq
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[tails[mid]] < v:
                lo = mid + 1
            else:
                hi = mid
        if lo > 0:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    # reconstruct LIS as indices into seq
    lis_indices: list[int] = []
    k = tails[-1] if tails else -1
    while k != -1:
        lis_indices.append(k)
        k = prev[k]
    lis_indices.reverse()
    return lis_indices


def absolute_position(position: str, path: str):
    if position:
        return f"{position}.{path}"
    else:
        return path


def calc_relative_path(relative_to: str, position: str):
    assert position.startswith(relative_to), (
        f"Cannot take relative path of {position} compared to {relative_to}"
    )
    position = position[len(relative_to) :]
    if position.startswith("."):
        position = position[1:]
    return position


def join_path(prefix: str, path: str | int):
    if prefix:
        return f"{prefix}.{path}"
    else:
        return str(path)
