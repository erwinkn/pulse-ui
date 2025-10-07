from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple, Sequence, cast

from pulse.css import CssReference
from pulse.helpers import values_equal
from pulse.reconciler import (
    InsertOperation,
    MoveOperation,
    RemoveOperation,
    ReplaceOperation,
    UpdateCallbacksDelta,
    UpdateCallbacksOperation,
    UpdateCssRefsDelta,
    UpdateCssRefsOperation,
    UpdatePropsDelta,
    UpdatePropsOperation,
    UpdateRenderPropsDelta,
    UpdateRenderPropsOperation,
    VDOMOperation,
)
from pulse.vdom import (
    Callback,
    Callbacks,
    ComponentNode,
    Element,
    Node,
    Props,
    VDOM,
    VDOMNode,
)

RenderPath = str


class RenderTree:
    root: Element
    callbacks: Callbacks
    render_props: set[str]
    css_refs: set[str]

    def __init__(self, root: Element) -> None:
        self.root = root
        self.callbacks = {}
        self.render_props = set()
        self.css_refs = set()
        self._normalized: Element | None = None

    def render(self) -> VDOM:
        renderer = Renderer()
        vdom, normalized = renderer.render_tree(self.root)
        self.root = normalized
        self.callbacks = renderer.callbacks
        self.render_props = renderer.render_props
        self.css_refs = renderer.css_refs
        self._normalized = normalized
        return vdom

    def diff(self, new_tree: Element) -> list[VDOMOperation]:
        if self._normalized is None:
            raise RuntimeError("RenderTree.render must be called before diff")

        renderer = Renderer()
        normalized = renderer.reconcile_tree(self._normalized, new_tree, path="")

        callback_prev = set(self.callbacks.keys())
        callback_next = set(renderer.callbacks.keys())
        callback_add = sorted(callback_next - callback_prev)
        callback_remove = sorted(callback_prev - callback_next)

        render_props_prev = self.render_props
        render_props_next = renderer.render_props
        render_props_add = sorted(render_props_next - render_props_prev)
        render_props_remove = sorted(render_props_prev - render_props_next)

        css_prev = self.css_refs
        css_next = renderer.css_refs
        css_add = sorted(css_next - css_prev)
        css_remove = sorted(css_prev - css_next)

        prefix: list[VDOMOperation] = []

        if css_add or css_remove:
            css_delta: UpdateCssRefsDelta = {}
            if css_add:
                css_delta["set"] = css_add
            if css_remove:
                css_delta["remove"] = css_remove
            prefix.append(
                UpdateCssRefsOperation(type="update_css_refs", path="", data=css_delta)
            )

        if callback_add or callback_remove:
            callback_delta: UpdateCallbacksDelta = {}
            if callback_add:
                callback_delta["add"] = callback_add
            if callback_remove:
                callback_delta["remove"] = callback_remove
            prefix.append(
                UpdateCallbacksOperation(
                    type="update_callbacks", path="", data=callback_delta
                )
            )

        if render_props_add or render_props_remove:
            render_props_delta: UpdateRenderPropsDelta = {}
            if render_props_add:
                render_props_delta["add"] = render_props_add
            if render_props_remove:
                render_props_delta["remove"] = render_props_remove
            prefix.append(
                UpdateRenderPropsOperation(
                    type="update_render_props", path="", data=render_props_delta
                )
            )

        ops = prefix + renderer.operations if prefix else renderer.operations

        self.callbacks = renderer.callbacks
        self.render_props = renderer.render_props
        self.css_refs = renderer.css_refs
        self._normalized = normalized
        self.root = normalized

        return ops

    def unmount(self) -> None:
        if self._normalized is not None:
            unmount_element(self._normalized)
            self._normalized = None
        self.callbacks.clear()
        self.render_props.clear()
        self.css_refs.clear()


@dataclass(slots=True)
class DiffPropsResult:
    normalized: Props
    delta_set: Props
    delta_remove: set[str]
    render_prop_reconciles: list["RenderPropTask"]


class RenderPropTask(NamedTuple):
    key: str
    previous: Element
    current: Element
    path: RenderPath


class Renderer:
    def __init__(self) -> None:
        self.callbacks: Callbacks = {}
        self.render_props: set[str] = set()
        self.css_refs: set[str] = set()
        self.operations: list[VDOMOperation] = []

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def render_tree(
        self, node: Element, *, path: RenderPath = ""
    ) -> tuple[VDOM, Element]:
        if isinstance(node, ComponentNode):
            return self._render_component(node, path=path)
        if isinstance(node, Node):
            return self._render_element(node, path=path)
        return node, node

    def _render_component(
        self, component: ComponentNode, *, path: RenderPath
    ) -> tuple[VDOM, ComponentNode]:
        with component.hooks:
            rendered = component.fn(*component.args, **component.kwargs)
        vdom, normalized_child = self.render_tree(rendered, path=path)
        component.contents = normalized_child
        return vdom, component

    def _render_element(
        self, element: Node, *, path: RenderPath
    ) -> tuple[VDOMNode, Node]:
        vdom_node: VDOMNode = {"tag": element.tag}
        if element.key is not None:
            vdom_node["key"] = element.key

        props = element.props or {}
        props_result = self.diff_props(previous={}, current=props, path=path)
        if props_result.delta_set:
            vdom_node["props"] = props_result.delta_set

        for task in props_result.render_prop_reconciles:
            normalized_value = self.reconcile_tree(
                task.previous, task.current, path=task.path
            )
            props_result.normalized[task.key] = normalized_value

        element.props = props_result.normalized or None

        children_vdom: list[VDOM] = []
        normalized_children: list[Element] = []
        for idx, child in enumerate(normalize_children(element.children)):
            child_path = join_path(path, idx)
            child_vdom, normalized_child = self.render_tree(child, path=child_path)
            children_vdom.append(child_vdom)
            normalized_children.append(normalized_child)

        if children_vdom:
            vdom_node["children"] = children_vdom
        element.children = normalized_children

        return vdom_node, element

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile_tree(
        self,
        previous: Element,
        current: Element,
        *,
        path: RenderPath = "",
    ) -> Element:
        if not same_node(previous, current):
            unmount_element(previous)
            new_vdom, normalized = self.render_tree(current, path=path)
            self.operations.append(
                ReplaceOperation(type="replace", path=path, data=new_vdom)
            )
            return normalized

        if isinstance(previous, ComponentNode) and isinstance(current, ComponentNode):
            return self.reconcile_component(previous, current, path=path)

        if isinstance(previous, Node) and isinstance(current, Node):
            return self.reconcile_element(previous, current, path=path)

        return current

    def reconcile_component(
        self,
        previous: ComponentNode,
        current: ComponentNode,
        *,
        path: RenderPath,
    ) -> ComponentNode:
        current.hooks = previous.hooks
        current.contents = previous.contents

        with current.hooks:
            rendered = current.fn(*current.args, **current.kwargs)

        if current.contents is None:
            new_vdom, normalized = self.render_tree(rendered, path=path)
            current.contents = normalized
            self.operations.append(
                ReplaceOperation(type="replace", path=path, data=new_vdom)
            )
        else:
            current.contents = self.reconcile_tree(
                current.contents, rendered, path=path
            )

        return current

    def reconcile_element(
        self,
        previous: Node,
        current: Node,
        *,
        path: RenderPath,
    ) -> Node:
        prev_props = previous.props or {}
        new_props = current.props or {}
        props_result = self.diff_props(
            previous=prev_props, current=new_props, path=path
        )

        if props_result.delta_set or props_result.delta_remove:
            delta: UpdatePropsDelta = {}
            if props_result.delta_set:
                delta["set"] = props_result.delta_set
            if props_result.delta_remove:
                delta["remove"] = sorted(props_result.delta_remove)
            self.operations.append(
                UpdatePropsOperation(type="update_props", path=path, data=delta)
            )

        for task in props_result.render_prop_reconciles:
            normalized_value = self.reconcile_tree(
                task.previous, task.current, path=task.path
            )
            props_result.normalized[task.key] = normalized_value

        prev_children = normalize_children(previous.children)
        next_children = normalize_children(current.children)
        normalized_children = self.reconcile_children(
            prev_children, next_children, path=path
        )

        # Mutate the current node to avoid allocations
        current.props = props_result.normalized or None
        current.children = normalized_children
        return current

    def reconcile_children(
        self,
        previous_children: Sequence[Element],
        new_children: Sequence[Element],
        *,
        path: RenderPath,
    ) -> list[Element]:
        if not previous_children and not new_children:
            return []

        has_keys = any(extract_key(child) is not None for child in new_children)
        if has_keys:
            return self.reconcile_children_keyed(
                previous_children, new_children, path=path
            )
        return self.reconcile_children_unkeyed(
            previous_children, new_children, path=path
        )

    def reconcile_children_keyed(
        self,
        previous_children: Sequence[Element],
        new_children: Sequence[Element],
        *,
        path: RenderPath,
    ) -> list[Element]:
        old_children = list(previous_children)
        new_children_list = list(new_children)
        old_len = len(old_children)
        new_len = len(new_children_list)

        normalized: list[Element | None] = [None] * new_len

        old_start = 0
        new_start = 0
        old_end = old_len - 1
        new_end = new_len - 1

        # Head sync
        while old_start <= old_end and new_start <= new_end:
            old_child = old_children[old_start]
            new_child = new_children_list[new_start]
            if not same_node(old_child, new_child):
                break
            child_path = join_path(path, new_start)
            normalized_child = self.reconcile_tree(
                old_child, new_child, path=child_path
            )
            normalized[new_start] = normalized_child
            old_start += 1
            new_start += 1

        # Tail sync
        while old_start <= old_end and new_start <= new_end:
            old_child = old_children[old_end]
            new_child = new_children_list[new_end]
            if not same_node(old_child, new_child):
                break
            child_path = join_path(path, new_end)
            normalized_child = self.reconcile_tree(
                old_child, new_child, path=child_path
            )
            normalized[new_end] = normalized_child
            old_end -= 1
            new_end -= 1

        # Old exhausted -> pure inserts
        if old_start > old_end:
            for idx in range(new_start, new_end + 1):
                child = new_children_list[idx]
                child_path = join_path(path, idx)
                vdom_child, normalized_child = self.render_tree(child, path=child_path)
                self.operations.append(
                    InsertOperation(type="insert", path=path, idx=idx, data=vdom_child)
                )
                normalized[idx] = normalized_child
            return [cast(Element, child) for child in normalized]

        # New exhausted -> pure removals
        if new_start > new_end:
            for idx in range(old_end, old_start - 1, -1):
                self.operations.append(
                    RemoveOperation(type="remove", path=path, idx=idx)
                )
                unmount_element(old_children[idx])
            return [cast(Element, child) for child in normalized if child is not None]

        key_to_new_index: dict[str, int] = {}
        for idx in range(new_start, new_end + 1):
            key_to_new_index[child_key(new_children_list[idx], idx)] = idx

        to_be_patched = new_end - new_start + 1
        new_index_to_old_index = [0] * to_be_patched
        patched = 0
        removals: list[int] = []

        # Defer reconciliation for nodes that will move; reconcile stable nodes immediately
        pending_reconciles: list[tuple[int, Element, Element]] = []
        for old_idx in range(old_start, old_end + 1):
            old_child = old_children[old_idx]
            key = child_key(old_child, old_idx)
            new_idx = key_to_new_index.get(key)
            if new_idx is None:
                removals.append(old_idx)
                continue

            window_index = new_idx - new_start
            new_index_to_old_index[window_index] = old_idx + 1
            patched += 1

            if new_idx == old_idx:
                # Stable position -> reconcile in place now
                child_path = join_path(path, new_idx)
                normalized_child = self.reconcile_tree(
                    old_child, new_children_list[new_idx], path=child_path
                )
                normalized[new_idx] = normalized_child
            else:
                # Will move -> place old child and reconcile after moves so paths are correct
                normalized[new_idx] = old_child
                pending_reconciles.append(
                    (new_idx, old_child, new_children_list[new_idx])
                )

            if patched == to_be_patched:
                for remaining in range(old_idx + 1, old_end + 1):
                    removals.append(remaining)
                break

        dom_keys = [child_key(child, idx) for idx, child in enumerate(old_children)]

        for old_idx in sorted(removals, reverse=True):
            self.operations.append(
                RemoveOperation(type="remove", path=path, idx=old_idx)
            )
            unmount_element(old_children[old_idx])
            if 0 <= old_idx < len(dom_keys):
                dom_keys.pop(old_idx)

        for new_idx in range(new_start, new_end + 1):
            new_child = new_children_list[new_idx]
            identifier = child_key(new_child, new_idx)
            mapped_value = new_index_to_old_index[new_idx - new_start]

            if mapped_value == 0:
                child_path = join_path(path, new_idx)
                vdom_child, normalized_child = self.render_tree(
                    new_child, path=child_path
                )
                self.operations.append(
                    InsertOperation(
                        type="insert", path=path, idx=new_idx, data=vdom_child
                    )
                )
                normalized[new_idx] = normalized_child
                dom_keys.insert(new_idx, identifier)
                continue

            try:
                current_index = dom_keys.index(identifier)
            except ValueError:
                continue

            if current_index == new_idx:
                continue

            self.operations.append(
                MoveOperation(
                    type="move",
                    path=path,
                    data={"from_index": current_index, "to_index": new_idx},
                )
            )
            dom_keys.pop(current_index)
            dom_keys.insert(new_idx, identifier)

        # Reconcile any moved children now, so inner updates target post-move paths
        for idx, prev_child, curr_child in pending_reconciles:
            child_path = join_path(path, idx)
            normalized_child = self.reconcile_tree(
                prev_child, curr_child, path=child_path
            )
            normalized[idx] = normalized_child

        assert all(child is not None for child in normalized)
        return [cast(Element, child) for child in normalized]

    def reconcile_children_unkeyed(
        self,
        previous_children: Sequence[Element],
        new_children: Sequence[Element],
        *,
        path: RenderPath,
    ) -> list[Element]:
        normalized: list[Element] = []
        shared = min(len(previous_children), len(new_children))

        for idx in range(shared):
            child_path = join_path(path, idx)
            normalized_child = self.reconcile_tree(
                previous_children[idx], new_children[idx], path=child_path
            )
            normalized.append(normalized_child)

        for idx in range(len(previous_children) - 1, shared - 1, -1):
            self.operations.append(RemoveOperation(type="remove", path=path, idx=idx))
            unmount_element(previous_children[idx])

        for idx in range(shared, len(new_children)):
            child_path = join_path(path, idx)
            vdom_child, normalized_child = self.render_tree(
                new_children[idx], path=child_path
            )
            self.operations.append(
                InsertOperation(type="insert", path=path, idx=idx, data=vdom_child)
            )
            normalized.append(normalized_child)

        return normalized

    # ------------------------------------------------------------------
    # Prop diffing
    # ------------------------------------------------------------------

    def diff_props(
        self,
        *,
        previous: Props,
        current: Props,
        path: RenderPath,
    ) -> DiffPropsResult:
        updated: Props = {}
        normalized: Props | None = None
        render_prop_tasks: list[RenderPropTask] = []
        removed_keys = set(previous.keys()) - set(current.keys())

        for key, value in current.items():
            old_value = previous.get(key)
            prop_path = join_path(path, key)

            if callable(value):
                if isinstance(old_value, (Node, ComponentNode)):
                    unmount_element(old_value)
                if normalized is None:
                    normalized = current.copy()
                normalized[key] = "$cb"
                register_callback(
                    self.callbacks, prop_path, cast(Callable[..., Any], value)
                )
                if old_value != "$cb":
                    updated[key] = "$cb"
                continue

            if isinstance(value, CssReference):
                if isinstance(old_value, (Node, ComponentNode)):
                    unmount_element(old_value)
                if normalized is None:
                    normalized = current.copy()
                normalized[key] = value
                self.css_refs.add(prop_path)
                if not isinstance(old_value, CssReference) or old_value != value:
                    updated[key] = _css_ref_token(value)
                continue

            if isinstance(value, (Node, ComponentNode)):
                if normalized is None:
                    normalized = current.copy()
                self.render_props.add(prop_path)
                if isinstance(old_value, (Node, ComponentNode)):
                    normalized[key] = old_value
                    render_prop_tasks.append(
                        RenderPropTask(
                            key=key,
                            previous=old_value,
                            current=value,
                            path=prop_path,
                        )
                    )
                else:
                    vdom_value, normalized_value = self.render_tree(
                        value, path=prop_path
                    )
                    normalized[key] = normalized_value
                    updated[key] = vdom_value
                continue

            if isinstance(old_value, (Node, ComponentNode)):
                unmount_element(old_value)

            if normalized is not None:
                normalized[key] = value

            if key not in previous or not values_equal(value, old_value):
                updated[key] = value

        for key in removed_keys:
            old_value = previous.get(key)
            if isinstance(old_value, (Node, ComponentNode)):
                unmount_element(old_value)

        normalized_props = normalized if normalized is not None else current.copy()
        return DiffPropsResult(
            normalized=normalized_props,
            delta_set=updated,
            delta_remove=removed_keys,
            render_prop_reconciles=render_prop_tasks,
        )

    # ------------------------------------------------------------------
    # Unmount helper
    # ------------------------------------------------------------------

    def unmount_subtree(self, node: Element) -> None:
        unmount_element(node)


def extract_key(element: Element) -> str | None:
    if isinstance(element, ComponentNode):
        return element.key
    if isinstance(element, Node):
        return element.key
    return None


def child_key(element: Element, index: int) -> str:
    key = extract_key(element)
    if key is not None:
        return key
    return f"__idx__{index}"


def normalize_children(children: Sequence[Element] | None) -> list[Element]:
    if not children:
        return []
    return list(children)


def register_callback(
    callbacks: Callbacks,
    path: RenderPath,
    fn: Callable[..., Any],
) -> None:
    n_args = len(inspect.signature(fn).parameters)
    callbacks[path] = Callback(fn=fn, n_args=n_args)


def join_path(prefix: RenderPath, path: str | int) -> RenderPath:
    if prefix:
        return f"{prefix}.{path}"
    return str(path)


def same_node(left: Element, right: Element) -> bool:
    if values_equal(left, right):
        return True
    if isinstance(left, Node) and isinstance(right, Node):
        return left.tag == right.tag and left.key == right.key
    if isinstance(left, ComponentNode) and isinstance(right, ComponentNode):
        return left.fn == right.fn and left.key == right.key
    return False


def lis(seq: list[int]) -> list[int]:
    if not seq:
        return []
    tails: list[int] = []
    prev: list[int] = [-1] * len(seq)
    for i, v in enumerate(seq):
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
    lis_indices: list[int] = []
    k = tails[-1] if tails else -1
    while k != -1:
        lis_indices.append(k)
        k = prev[k]
    lis_indices.reverse()
    return lis_indices


def _css_ref_token(ref: CssReference) -> str:
    return f"{ref.module.id}:{ref.name}"


def unmount_element(element: Element) -> None:
    if isinstance(element, ComponentNode):
        if element.contents is not None:
            unmount_element(element.contents)
            element.contents = None
        element.hooks.unmount()
        return

    if isinstance(element, Node):
        props = element.props or {}
        for value in props.values():
            if isinstance(value, (Node, ComponentNode)):
                unmount_element(value)
        for child in normalize_children(element.children):
            unmount_element(child)
        element.children = []
        return

    # Primitive -> nothing to unmount
