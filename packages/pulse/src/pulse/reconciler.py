# Problems with the current reconciler:
# - We only have RenderNode for Pulse components. However in React, if you swap
#   two keyed elements, no matter what they are, that include stateful children,
#   the children's state is preserved. React properly moves around the full
#   tree. We could introduce a RenderNode for each element in the tree, but that
#   seems quite heavy. I think a better algorithm is needed.
# - We have very suboptimal keyed diffing, we should implement a Vue or morphdom
#   style longest increasing subsequence (LIS) algorithm.
# IMO I should probably read morphdom's source code.
import inspect
import warnings
from dataclasses import dataclass
from typing import (
    Callable,
    Iterable,
    Literal,
    NamedTuple,
    Optional,
    Sequence,
    TypedDict,
    Union,
    cast,
)

from pulse.css import CssReference
from pulse.helpers import values_equal
from pulse.hooks import HookContext
from pulse.reactive import Effect
from pulse.vdom import (
    VDOM,
    Callback,
    Callbacks,
    Child,
    Children,
    ComponentNode,
    Element,
    Node,
    Props,
    VDOMNode,
)


class InsertOperation(TypedDict):
    type: Literal["insert"]
    path: str
    idx: int
    data: VDOM


class RemoveOperation(TypedDict):
    type: Literal["remove"]
    idx: int
    path: str


class ReplaceOperation(TypedDict):
    type: Literal["replace"]
    path: str
    data: VDOM


class UpdatePropsOperation(TypedDict):
    type: Literal["update_props"]
    path: str
    data: "UpdatePropsDelta"


class UpdatePropsDelta(TypedDict, total=False):
    # Only send changed/new keys under `set` and removed keys under `remove`
    set: Props
    remove: list[str]


class UpdateCallbacksDelta(TypedDict, total=False):
    add: list[str]
    remove: list[str]


class UpdateCallbacksOperation(TypedDict):
    type: Literal["update_callbacks"]
    path: str
    data: UpdateCallbacksDelta


class UpdateCssRefsDelta(TypedDict, total=False):
    set: list[str]
    remove: list[str]


class UpdateCssRefsOperation(TypedDict):
    type: Literal["update_css_refs"]
    path: str
    data: UpdateCssRefsDelta


class UpdateRenderPropsDelta(TypedDict, total=False):
    add: list[str]
    remove: list[str]


class UpdateRenderPropsOperation(TypedDict):
    type: Literal["update_render_props"]
    path: str
    data: UpdateRenderPropsDelta


class MoveOperationData(TypedDict):
    from_index: int
    to_index: int


class MoveOperation(TypedDict):
    type: Literal["move"]
    path: str
    data: MoveOperationData


VDOMOperation = Union[
    InsertOperation,
    RemoveOperation,
    ReplaceOperation,
    UpdatePropsOperation,
    MoveOperation,
    UpdateCallbacksOperation,
    UpdateCssRefsOperation,
    UpdateRenderPropsOperation,
]


@dataclass
class RenderDiff:
    tree: Element
    render_count: int
    callbacks: Callbacks
    render_props: set[str]
    css_refs: set[str]
    ops: list[VDOMOperation]


class RenderRoot:
    render_tree: "RenderNode"
    render_count: int
    callbacks: Callbacks
    render_props: set[str]
    css_refs: set[str]
    effect: Effect | None

    def __init__(self, fn: Callable[[], Element]) -> None:
        self.render_tree = RenderNode(fn)
        self.callbacks = {}
        self.render_props = set()
        self.css_refs = set()
        self.effect = None
        self.render_count = 0
        pass

    def render_diff(self) -> RenderDiff:
        self.render_count += 1
        resolver = Resolver()
        last_render = self.render_tree.last_render
        new_tree = self.render_tree.render()
        new_tree = resolver.reconcile_node(
            render_parent=self.render_tree, old_tree=last_render, new_tree=new_tree
        )
        self.render_tree.last_render = new_tree
        prev_cb = set(self.callbacks.keys())
        new_cb = set(resolver.callbacks.keys())
        cb_added = sorted(new_cb - prev_cb)
        cb_removed = sorted(prev_cb - new_cb)

        prev_rp = self.render_props
        new_rp = resolver.render_props
        rp_added = sorted(new_rp - prev_rp)
        rp_removed = sorted(prev_rp - new_rp)

        prev_css = self.css_refs
        new_css = resolver.css_refs
        css_added = sorted(new_css - prev_css)
        css_removed = sorted(prev_css - new_css)

        ops = list(resolver.operations)
        prefix_ops: list[VDOMOperation] = []

        if css_added or css_removed:
            css_delta: UpdateCssRefsDelta = {}
            if css_added:
                css_delta["set"] = css_added
            if css_removed:
                css_delta["remove"] = css_removed
            prefix_ops.append(
                UpdateCssRefsOperation(type="update_css_refs", path="", data=css_delta)
            )

        if cb_added or cb_removed:
            cb_delta: UpdateCallbacksDelta = {}
            if cb_added:
                cb_delta["add"] = cb_added
            if cb_removed:
                cb_delta["remove"] = cb_removed
            prefix_ops.append(
                UpdateCallbacksOperation(
                    type="update_callbacks", path="", data=cb_delta
                )
            )

        if rp_added or rp_removed:
            rp_delta: UpdateRenderPropsDelta = {}
            if rp_added:
                rp_delta["add"] = rp_added
            if rp_removed:
                rp_delta["remove"] = rp_removed
            prefix_ops.append(
                UpdateRenderPropsOperation(
                    type="update_render_props", path="", data=rp_delta
                )
            )

        if prefix_ops:
            ops = prefix_ops + ops

        self.callbacks = resolver.callbacks
        self.render_props = resolver.render_props
        self.css_refs = new_css
        return RenderDiff(
            tree=new_tree,
            render_count=self.render_count,
            callbacks=resolver.callbacks,
            render_props=resolver.render_props,
            css_refs=new_css,
            ops=ops,
        )

    def render_vdom(self) -> tuple[VDOM, Callbacks, set[str], set[str], set[str]]:
        """One-shot render to VDOM + callbacks + render_props, without mounting an Effect."""
        self.render_count += 1
        resolver = Resolver()
        # Fresh render of the root component into a VDOM tree
        vdom, normalized = resolver.render_tree(
            render_parent=self.render_tree,
            node=self.render_tree.render(),
        )
        self.render_tree.last_render = normalized
        self.callbacks = resolver.callbacks
        self.render_props = resolver.render_props
        self.css_refs = resolver.css_refs
        return vdom, self.callbacks, self.render_props, self.css_refs

    def unmount(self) -> None:
        if self.effect is not None:
            self.effect.dispose()
            self.effect = None
        # Unmount tree to dispose hooks/effects recursively
        if self.render_tree is not None:
            self.render_tree.unmount()


class RenderNode:
    fn: Callable[..., Element]
    hooks: HookContext
    last_render: Element
    key: Optional[str]
    # Absolute position in the tree
    children: dict[str, "RenderNode"]

    def __init__(self, fn: Callable[..., Element], key: Optional[str] = None) -> None:
        self.fn = fn
        self.hooks = HookContext()
        self.last_render = None
        self.children = {}
        self.key = key

    def render(self, *args, **kwargs) -> Element:
        # Render result needs to be normalized before reassigned to self.last_render
        with self.hooks:
            return self.fn(*args, **kwargs)

    def unmount(self):
        self.hooks.unmount()
        for child in self.children.values():
            child.unmount()


class DiffPropsResult(NamedTuple):
    normalized: Props
    delta_add: Props
    delta_remove: set[str]


class Resolver:
    def __init__(self) -> None:
        self.callbacks: Callbacks = {}
        self.render_props: set[str] = set()
        self.css_refs: set[str] = set()
        self.operations: list[VDOMOperation] = []

    def reconcile_node(
        self,
        render_parent: RenderNode,
        old_tree: Element,
        new_tree: Element,
        path="",
        relative_path="",
    ) -> Element:
        if not same_node(old_tree, new_tree):
            # If we're replacing a ComponentNode, unmount the old one before
            # rendering the new.
            # NOTE: with our hack of only preserving component state during
            # keyed reconciliation, we will encounter scenarios where the render
            # node has already been moved here.
            if (
                isinstance(old_tree, ComponentNode)
                and relative_path in render_parent.children
            ):
                # HACK due to our general keyed reconciliation hack
                old_render_child = render_parent.children[relative_path]
                if old_render_child.key == old_tree.key:
                    render_parent.children.pop(relative_path).unmount()
            new_vdom, normalized = self.render_tree(
                render_parent=render_parent,
                node=new_tree,
                path=path,
                relative_path=relative_path,
            )
            self.operations.append(
                ReplaceOperation(type="replace", path=path, data=new_vdom)
            )
            return normalized

        # At this point, we are dealing with the same node. We need to diff its props + its children
        if isinstance(old_tree, Node):
            assert isinstance(new_tree, Node)
            # Sanitize props (capture callbacks & render props in single pass)
            props_diff = self.diff_props(
                path=path,
                old_props=old_tree.props or {},
                new_props=new_tree.props or {},
                render_parent=render_parent,
                relative_path=relative_path,
            )
            delta: UpdatePropsDelta = {}
            if props_diff.delta_add:
                delta["set"] = props_diff.delta_add
            if props_diff.delta_remove:
                delta["remove"] = sorted(props_diff.delta_remove)
            if delta:
                self.operations.append(
                    UpdatePropsOperation(type="update_props", path=path, data=delta)
                )
            normalized_children: list[Element] = []
            if old_tree.children or new_tree.children:
                # Ensure new children are a flat list before diffing so that
                # we can safely compute lengths and indices.
                if new_tree.children:
                    new_children_list = _flatten_children(
                        cast(Children, new_tree.children),
                        parent_tag=new_tree.tag,
                        path=path,
                    )
                else:
                    new_children_list = []
                # old_tree.children should already be normalized Element items,
                # but it is typed as Children; cast for the type checker.
                old_children_list = cast(Sequence[Element], old_tree.children or [])
                normalized_children = self.reconcile_children(
                    render_parent=render_parent,
                    old_children=old_children_list,
                    new_children=new_children_list,
                    path=path,
                    relative_path=relative_path,
                )
            return Node(
                tag=new_tree.tag,
                props=props_diff.normalized or None,
                children=normalized_children or None,
                key=new_tree.key,
            )

        if isinstance(old_tree, ComponentNode):
            assert (
                isinstance(new_tree, ComponentNode)
                and old_tree.fn == new_tree.fn
                and old_tree.key == new_tree.key
            )
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
        old_children: Sequence[Element],
        new_children: Sequence[Element],
        path: str,
        relative_path: str,
    ) -> list[Element]:
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
        old_children: Sequence[Element],
        new_children: Sequence[Element],
        path: str,
        relative_path: str,
    ) -> list[Element]:
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

            if node.key:
                old_keys[node.key] = old_idx

        # Determine which keys are present in the new children
        new_keys: set[str] = {
            key
            for node in new_children
            if isinstance(node, ComponentNode)
            for key in [getattr(node, "key", None)]
            if key is not None
        }

        # Unmount any components that were present before but are now removed
        # BEFORE we remap/move nodes, so we don't lose references by overwrite.
        for key, old_idx in old_keys.items():
            if key not in new_keys:
                old_path = join_path(relative_path, old_idx)
                old_render_node = render_parent.children.pop(old_path, None)
                if old_render_node is not None:
                    old_render_node.unmount()

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
                    # It's possible the old_path was already popped if it was
                    # removed; guard with .pop(..., None)
                    moved_node = render_parent.children.pop(old_path, None)
                    if moved_node is not None:
                        remap[new_path] = moved_node
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
        old_children: Sequence[Element],
        new_children: Sequence[Element],
        path: str,
        relative_path: str,
    ) -> list[Element]:
        N_shared = min(len(old_children), len(new_children))
        normalized_children: list[Element] = []
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

        # Only runs if there are more old nodes than new ones.
        # Emit removes in descending index order to avoid index shifts
        # when consumers apply operations sequentially.
        for i in range(len(old_children) - 1, N_shared - 1, -1):
            old_child = old_children[i]
            if isinstance(old_child, ComponentNode):
                # TODO in tests: verify that components are unmounted correctly
                old_rel_path = join_path(relative_path, i)
                old_render_node = render_parent.children.get(old_rel_path)
                # The render node may have been moved earlier during keyed
                # reconciliation. Only unmount if it still exists at this
                # location and corresponds to the same key.
                if old_render_node is not None and old_render_node.key == old_child.key:
                    old_render_node.unmount()
            self.operations.append(RemoveOperation(type="remove", path=path, idx=i))

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
                InsertOperation(type="insert", path=path, idx=i, data=new_vdom)
            )
            normalized_children.append(norm_child)

        return normalized_children

    def render_tree(
        self,
        render_parent: RenderNode,
        node: Element,
        path: str = "",
        relative_path: str = "",
    ) -> tuple[VDOM, Element]:
        if isinstance(node, ComponentNode):
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
            normalized_props = node.props
            if node.props:
                diff_props = self.diff_props(
                    path=path,
                    old_props={},
                    new_props=node.props,
                    render_parent=render_parent,
                    relative_path=relative_path,
                )
                if diff_props.delta_add:
                    vdom_node["props"] = diff_props.delta_add
                normalized_props = diff_props.normalized or None
            # Preserve lazy flag if present
            if node.lazy:
                vdom_node["lazy"] = True
            normalized_children: list[Element] | None = None
            if node.children:
                # Flatten any iterable children (e.g., generators, lists) one or more levels deep
                flat_children = _flatten_children(
                    node.children, parent_tag=node.tag, path=path
                )
                v_children: list[VDOM] = []
                normalized_children = []
                for i, child in enumerate(flat_children):
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
                props=normalized_props,
                children=normalized_children or None,
                key=node.key,
                lazy=node.lazy,
            )
            return vdom_node, normalized_node
        else:
            return node, node

    def diff_props(
        self,
        path: str,
        old_props: Props,
        new_props: Props,
        render_parent: RenderNode,
        relative_path: str,
    ):
        updated: Props = {}
        normalized: Props | None = None
        removed = set(old_props.keys()) - set(new_props.keys())

        for key, value in new_props.items():
            old_value = old_props.get(key)
            prop_path = join_path(path, key)
            prop_relative = join_path(relative_path, key)
            # Callback
            if callable(value):
                if normalized is None:
                    normalized = new_props.copy()
                normalized.pop(key)
                self.callbacks[prop_path] = Callback(
                    fn=value, n_args=len(inspect.signature(value).parameters)
                )
                continue

            if isinstance(value, CssReference):
                if normalized is None:
                    normalized = new_props.copy()
                token = _css_ref_token(value)
                normalized[key] = value
                self.css_refs.add(prop_path)
                if old_value != value:
                    updated[key] = token
                continue

            # Render prop (Pulse element)
            if isinstance(value, (Node, ComponentNode)):
                if normalized is None:
                    normalized = new_props.copy()

                self.render_props.add(prop_path)
                if isinstance(old_value, (Node, ComponentNode)):
                    normalized[key] = self.reconcile_node(
                        render_parent=render_parent,
                        old_tree=old_value,
                        new_tree=value,
                        path=prop_path,
                        relative_path=prop_relative,
                    )
                else:
                    self._unmount_render_subtree(render_parent, prop_relative)
                    vdom_value, normalized_value = self.render_tree(
                        render_parent=render_parent,
                        node=value,
                        path=prop_path,
                        relative_path=prop_relative,
                    )
                    normalized[key] = normalized_value
                    updated[key] = vdom_value
                continue

            # Regular prop
            if isinstance(old_value, (Node, ComponentNode)):
                self._unmount_render_subtree(render_parent, prop_relative)
            if key not in old_props or not values_equal(value, old_props[key]):
                updated[key] = value
            # No need to set normalized[key] = value as the value will be copied over through new_props.copy() if normalized is instantiated

        for key in removed:
            old_value = old_props.get(key)
            if isinstance(old_value, (Node, ComponentNode)):
                self._unmount_render_subtree(
                    render_parent, join_path(relative_path, key)
                )

        if normalized is not None:
            normalized_props = normalized
        else:
            normalized_props = new_props

        return DiffPropsResult(
            normalized=normalized_props, delta_add=updated, delta_remove=removed
        )

    def _unmount_render_subtree(self, parent: RenderNode, prefix: str) -> None:
        if not prefix:
            # Defensive: never clear the whole tree from here
            return
        keys_to_remove = [
            key
            for key in list(parent.children.keys())
            if key == prefix or key.startswith(f"{prefix}.")
        ]
        for key in keys_to_remove:
            render_child = parent.children.pop(key, None)
            if render_child is not None:
                render_child.unmount()

    # --- Internal helpers -----------------------------------------------------


def _flatten_children(
    children: Children, *, parent_tag: str, path: str
) -> list[Element]:
    flat: list[Element] = []

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
                        "[Pulse] Iterable children of <{}> at path '{}' contain elements without 'key'. "
                        "Add a stable 'key' to each element inside iterables to improve reconciliation."
                    ).format(parent_tag, path),
                    stacklevel=3,
                )
        else:
            # Not an iterable child: must be a Element or primitive
            flat.append(item)

    for child in children:
        visit(child)

    return flat


def same_node(left: Element, right: Element):
    # Handles primitive equality safely (avoid ambiguous truthiness for array-like)
    if values_equal(left, right):
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


def _css_ref_token(ref: CssReference) -> str:
    return f"{ref.module.id}:{ref.name}"
