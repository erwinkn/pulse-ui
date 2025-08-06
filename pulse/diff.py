"""
VDOM diffing algorithm for server-side reactive updates.

This module provides pure functions for comparing VDOM trees and generating
minimal update sequences. The diffing algorithm handles keyed reconciliation
similar to React's diffing algorithm.
"""

from typing import (
    List,
    TypedDict,
    Union,
    Optional,
    Literal,
    Sequence,
)
from .vdom import VDOM, Props


class InsertOperation(TypedDict):
    type: Literal["insert"]
    path: str
    data: VDOM


class RemoveOperation(TypedDict):
    type: Literal["remove"]
    path: str
    data: Optional[str]  # optional key, for keyed removals


class ReplaceOperation(TypedDict):
    type: Literal["replace"]
    path: str
    data: VDOM


class UpdatePropsOperation(TypedDict):
    type: Literal["update_props"]
    path: str
    data: Props


class MoveOperationData(TypedDict):
    from_index: int
    to_index: int
    key: str


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
]


def diff_vdom(
    old_node: Optional[VDOM], new_node: Optional[VDOM], path: str = ""
) -> list[VDOMOperation]:
    """
    Main VDOM diffing function that compares two VDOM trees and produces update operations.

    Args:
        old_node: The previous VDOM or primitive (or None for initial render)
        new_node: The new VDOM or primitive (or None for removal)
        path: Current path in the tree (dot-separated string)

    Returns:
        A list of VDOM operations.
    """
    operations: list[VDOMOperation] = []

    # Handle null cases
    if old_node is None and new_node is None:
        return operations
    elif old_node is None:
        assert new_node is not None  # Type guard
        operations.append({"type": "insert", "path": path, "data": new_node})
        return operations
    elif new_node is None:
        operations.append({"type": "remove", "path": path, "data": None})
        return operations

    # Both exist - check if they're the same
    if old_node == new_node:
        return operations

    # Same Node - diff recursively
    if (
        isinstance(old_node, dict)
        and isinstance(new_node, dict)
        and old_node.get("tag") == new_node.get("tag")
    ):
        # Same tag - check props and children directly
        old_props = old_node.get("props", {})
        new_props = new_node.get("props", {})
        if old_props != new_props:
            update_op: UpdatePropsOperation = {
                "type": "update_props",
                "path": path,
                "data": new_props,
            }
            operations.append(update_op)

        # Diff children recursively
        old_children = old_node.get("children", []) or []
        new_children = new_node.get("children", []) or []
        child_ops = _diff_node_children(old_children, new_children, path)
        operations.extend(child_ops)

        return operations
    else:
        # At least one is primitive or tags/types differ - replace
        replace_op: ReplaceOperation = {
            "type": "replace",
            "path": path,
            "data": new_node,
        }
        return [replace_op]


def _diff_node_children(
    old_children: Sequence[VDOM], new_children: Sequence[VDOM], path: str
) -> list[VDOMOperation]:
    """
    Diff VDOM children directly, avoiding double traversal.

    Args:
        old_children: Previous children (list of VDOM or primitives)
        new_children: New children (list of VDOM or primitives)
        path: Current path

    Returns:
        A list of VDOM operations.
    """
    operations = []

    # Check if we have any keyed nodes to determine strategy
    has_keyed_old = any(
        isinstance(child, dict) and "key" in child for child in old_children
    )
    has_keyed_new = any(
        isinstance(child, dict) and "key" in child for child in new_children
    )

    if has_keyed_old or has_keyed_new:
        # Use keyed reconciliation
        child_ops = _diff_keyed_node_children(old_children, new_children, path)
        operations.extend(child_ops)
    else:
        # Use positional reconciliation
        child_ops = _diff_positional_node_children(old_children, new_children, path)
        operations.extend(child_ops)

    return operations


def _diff_keyed_node_children(
    old_children: Sequence[VDOM], new_children: Sequence[VDOM], path: str
) -> list[VDOMOperation]:
    """Handle keyed VDOM children reconciliation."""
    operations = []

    # Build maps of keyed elements
    old_keyed = {}
    old_positions = {}
    new_keyed = {}

    for i, child in enumerate(old_children):
        if isinstance(child, dict) and "key" in child:
            old_keyed[child["key"]] = child
            old_positions[child["key"]] = i

    for i, child in enumerate(new_children):
        if isinstance(child, dict) and "key" in child:
            new_keyed[child["key"]] = child

    # Track which old positions are still used
    used_old_positions = set()

    # Process new children in order
    for new_index, new_child in enumerate(new_children):
        child_path = f"{path}.{new_index}" if path else str(new_index)

        if isinstance(new_child, dict) and "key" in new_child:
            key = new_child["key"]

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
                child_ops = diff_vdom(old_child, new_child, child_path)
                operations.extend(child_ops)
            else:
                # New keyed element - insert
                operations.append(
                    {"type": "insert", "path": child_path, "data": new_child}
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
                    isinstance(old_child_at_pos, dict) and "key" in old_child_at_pos
                )
            ):
                # Both unkeyed at same position - diff them
                old_child = old_children[new_index]
                used_old_positions.add(new_index)

                child_ops = diff_vdom(old_child, new_child, child_path)
                operations.extend(child_ops)
            else:
                # No matching element - insert
                operations.append(
                    {"type": "insert", "path": child_path, "data": new_child}
                )

    # Remove old keyed elements that are no longer present
    for key, old_child in old_keyed.items():
        if key not in new_keyed:
            old_index = old_positions[key]
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append({"type": "remove", "path": old_child_path, "data": key})

    # Handle unkeyed old elements that weren't replaced
    for old_index, old_child in enumerate(old_children):
        if old_index not in used_old_positions and not (
            isinstance(old_child, dict) and "key" in old_child
        ):
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append({"type": "remove", "path": old_child_path, "data": None})

    return operations


def _diff_positional_node_children(
    old_children: Sequence[VDOM], new_children: Sequence[VDOM], path: str
) -> list[VDOMOperation]:
    """Handle unkeyed VDOM children using positional diffing."""
    operations = []
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        child_path = f"{path}.{i}" if path else str(i)

        old_child = old_children[i] if i < len(old_children) else None
        new_child = new_children[i] if i < len(new_children) else None

        if old_child and new_child:
            # Both exist - diff them
            child_ops = diff_vdom(old_child, new_child, child_path)
            operations.extend(child_ops)
        elif new_child:
            # New child - insert
            operations.append({"type": "insert", "path": child_path, "data": new_child})
        else:
            # Old child that's no longer present - remove
            operations.append({"type": "remove", "path": child_path, "data": None})

    return operations


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
