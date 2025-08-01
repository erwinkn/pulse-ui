"""
VDOM diffing algorithm for server-side reactive updates.

This module provides pure functions for comparing VDOM trees and generating
minimal update sequences. The diffing algorithm handles keyed reconciliation
similar to React's diffing algorithm.
"""

from dataclasses import dataclass
from typing import (
    List,
    Any,
    NamedTuple,
    TypedDict,
    Union,
    Optional,
    Literal,
    Callable,
    Sequence,
)
from .vdom import VDOMNode, PrimitiveNode, Node, NodeChild


# Type aliases
Path = str
VDOM = Union[VDOMNode, PrimitiveNode]
Props = dict[str, Any]


class InsertOperation(TypedDict):
    type: Literal["insert"]
    path: Path
    data: VDOM


class RemoveOperation(TypedDict):
    type: Literal["remove"]
    path: Path
    data: Optional[str]  # optional key, for keyed removals


class ReplaceOperation(TypedDict):
    type: Literal["replace"]
    path: Path
    data: VDOM


class UpdatePropsOperation(TypedDict):
    type: Literal["update_props"]
    path: Path
    data: Props


class MoveOperationData(TypedDict):
    from_index: int
    to_index: int
    key: str


class MoveOperation(TypedDict):
    type: Literal["move"]
    path: Path
    data: MoveOperationData


VDOMOperation = Union[
    InsertOperation,
    RemoveOperation,
    ReplaceOperation,
    UpdatePropsOperation,
    MoveOperation,
]


# Payload sent to the client on updates
class Diff(NamedTuple):
    operations: list[VDOMOperation]
    callbacks: dict[str, Callable]


def _render_node_or_primitive(
    node: NodeChild, path: Path
) -> tuple[VDOM, dict[str, Callable]]:
    """
    Helper to render a Node to VDOM or return a primitive value directly.

    Args:
        node: Node or primitive value
        path: Path for callback registration

    Returns:
        Tuple of (VDOM, callbacks dict)
    """
    if isinstance(node, Node):
        vdom, callbacks = node.render(path)
        return vdom, callbacks
    else:
        return node, {}


def diff_vdom(
    old_node: Optional[NodeChild], new_node: Optional[NodeChild], path: Path = ""
) -> Diff:
    """
    Main VDOM diffing function that compares two Node trees and produces update operations.

    Args:
        old_node: The previous Node or primitive (or None for initial render)
        new_node: The new Node or primitive (or None for removal)
        path: Current path in the tree (dot-separated string)

    Returns:
        Diff with update operations and callback mapping
    """
    operations: list[VDOMOperation] = []
    callbacks: dict[str, Callable] = {}

    # Handle null cases
    if old_node is None and new_node is None:
        return Diff(operations, callbacks)
    elif old_node is None:
        # Insert new value
        assert new_node is not None  # Type guard
        vdom, callbacks = _render_node_or_primitive(new_node, path)
        insert_op: InsertOperation = {"type": "insert", "path": path, "data": vdom}
        operations = [insert_op]
        return Diff(operations, callbacks)
    elif new_node is None:
        # Remove old value
        remove_op: RemoveOperation = {"type": "remove", "path": path, "data": None}
        operations = [remove_op]
        return Diff(operations, {})

    # Both exist - check if they're the same
    if old_node == new_node:
        return Diff(operations, callbacks)

    # Same Node - diff recursively
    if (
        isinstance(old_node, Node)
        and isinstance(new_node, Node)
        and old_node.tag == new_node.tag
    ):
        # Same tag - check props and children directly
        old_props = old_node.props or {}
        new_props = new_node.props or {}
        if old_props != new_props:
            update_op: UpdatePropsOperation = {
                "type": "update_props",
                "path": path,
                "data": new_props,
            }
            operations.append(update_op)

        # Diff children recursively
        old_children = old_node.children or []
        new_children = new_node.children or []
        child_ops, child_callbacks = _diff_node_children(
            old_children, new_children, path
        )
        operations.extend(child_ops)
        callbacks.update(child_callbacks)

        return Diff(operations, callbacks)
    else:
        # At least one is primitive or tags/types differ - replace
        assert new_node is not None  # Type guard
        vdom, node_callbacks = _render_node_or_primitive(new_node, path)
        callbacks.update(node_callbacks)
        replace_op: ReplaceOperation = {"type": "replace", "path": path, "data": vdom}
        operations = [replace_op]
        return Diff(operations, callbacks)


def _diff_node_children(
    old_children: Sequence[NodeChild], new_children: Sequence[NodeChild], path: Path
) -> tuple[list[VDOMOperation], dict[str, Callable]]:
    """
    Diff Node children directly, avoiding double traversal.

    Args:
        old_children: Previous children (list of Node or primitives)
        new_children: New children (list of Node or primitives)
        path: Current path

    Returns:
        Tuple of (operations, callbacks)
    """
    operations = []
    callbacks = {}

    # Check if we have any keyed nodes to determine strategy
    has_keyed_old = any(
        isinstance(child, Node) and child.key is not None for child in old_children
    )
    has_keyed_new = any(
        isinstance(child, Node) and child.key is not None for child in new_children
    )

    if has_keyed_old or has_keyed_new:
        # Use keyed reconciliation
        child_ops, child_callbacks = _diff_keyed_node_children(
            old_children, new_children, path
        )
        operations.extend(child_ops)
        callbacks.update(child_callbacks)
    else:
        # Use positional reconciliation
        child_ops, child_callbacks = _diff_positional_node_children(
            old_children, new_children, path
        )
        operations.extend(child_ops)
        callbacks.update(child_callbacks)

    return operations, callbacks


def _diff_keyed_node_children(
    old_children: Sequence[NodeChild], new_children: Sequence[NodeChild], path: Path
) -> tuple[list[VDOMOperation], dict[str, Callable]]:
    """Handle keyed Node children reconciliation."""
    operations = []
    callbacks = {}

    # Build maps of keyed elements
    old_keyed = {}
    old_positions = {}
    new_keyed = {}

    for i, child in enumerate(old_children):
        if isinstance(child, Node) and child.key is not None:
            old_keyed[child.key] = child
            old_positions[child.key] = i

    for i, child in enumerate(new_children):
        if isinstance(child, Node) and child.key is not None:
            new_keyed[child.key] = child

    # Track which old positions are still used
    used_old_positions = set()

    # Process new children in order
    for new_index, new_child in enumerate(new_children):
        child_path = f"{path}.{new_index}" if path else str(new_index)

        if isinstance(new_child, Node) and new_child.key is not None:
            key = new_child.key

            if key in old_keyed:
                # Key exists in old children
                old_child = old_keyed[key]
                old_index = old_positions[key]
                used_old_positions.add(old_index)

                # Check if it moved
                if old_index != new_index:
                    operations.append(
                        {
                            "type": "move",
                            "path": child_path,
                            "data": {
                                "from_index": old_index,
                                "to_index": new_index,
                                "key": key,
                            },
                        }
                    )

                # Diff the moved/stayed element recursively
                child_diff = diff_vdom(old_child, new_child, child_path)
                operations.extend(child_diff.operations)
                callbacks.update(child_diff.callbacks)
            else:
                # New keyed element - insert and render
                vdom, child_callbacks = _render_node_or_primitive(new_child, child_path)
                callbacks.update(child_callbacks)
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": vdom,
                    }
                )
        else:
            # Unkeyed new element - try to match positionally
            old_child_at_pos = (
                old_children[new_index] if new_index < len(old_children) else None
            )
            if (
                new_index < len(old_children)
                and new_index not in used_old_positions
                and not (
                    isinstance(old_child_at_pos, Node)
                    and old_child_at_pos.key is not None
                )
            ):
                # Both unkeyed at same position - diff them
                old_child = old_children[new_index]
                used_old_positions.add(new_index)

                child_diff = diff_vdom(old_child, new_child, child_path)
                operations.extend(child_diff.operations)
                callbacks.update(child_diff.callbacks)
            else:
                # No matching element - insert
                vdom, child_callbacks = _render_node_or_primitive(new_child, child_path)
                callbacks.update(child_callbacks)
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": vdom,
                    }
                )

    # Remove old keyed elements that are no longer present
    for key, old_child in old_keyed.items():
        if key not in new_keyed:
            old_index = old_positions[key]
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append(
                {
                    "type": "remove",
                    "path": old_child_path,
                    "data": key,
                }
            )

    # Handle unkeyed old elements that weren't replaced
    for old_index, old_child in enumerate(old_children):
        if old_index not in used_old_positions and not (
            isinstance(old_child, Node) and old_child.key is not None
        ):
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append(
                {
                    "type": "remove",
                    "path": old_child_path,
                    "data": None,
                }
            )

    return operations, callbacks


def _diff_positional_node_children(
    old_children: Sequence[NodeChild], new_children: Sequence[NodeChild], path: Path
) -> tuple[list[VDOMOperation], dict[str, Callable]]:
    """Handle unkeyed Node children using positional diffing."""
    operations = []
    callbacks = {}
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        child_path = f"{path}.{i}" if path else str(i)

        if i < len(old_children) and i < len(new_children):
            # Both exist - diff them
            old_child = old_children[i]
            new_child = new_children[i]
            child_diff = diff_vdom(old_child, new_child, child_path)
            operations.extend(child_diff.operations)
            callbacks.update(child_diff.callbacks)

        elif i < len(new_children):
            # New child - insert
            new_child = new_children[i]
            vdom, child_callbacks = _render_node_or_primitive(new_child, child_path)
            callbacks.update(child_callbacks)
            operations.append(
                {
                    "type": "insert",
                    "path": child_path,
                    "data": vdom,
                }
            )

        else:
            # Old child that's no longer present - remove
            operations.append(
                {
                    "type": "remove",
                    "path": child_path,
                    "data": None,
                }
            )

    return operations, callbacks


def optimize_operations(operations: List[VDOMOperation]) -> List[VDOMOperation]:
    """
    Optimize a list of operations by removing redundant operations and merging where possible.

    Args:
        operations: List of operations to optimize

    Returns:
        Optimized list of operations
    """
    if not operations:
        return operations

    optimized = []

    # Remove duplicate operations and merge property updates
    for op in operations:
        # Skip no-op property updates (empty props)
        if op["type"] == "update_props" and op["data"] is not None and not op["data"]:
            continue

        # For now, just include all other operations
        # Future optimizations could include:
        # - Merging consecutive property updates on the same path
        # - Removing operations that are immediately overwritten by replace operations
        # - Coalescing insert/remove pairs into replace operations
        optimized.append(op)

    return optimized
