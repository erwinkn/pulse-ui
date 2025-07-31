"""
VDOM diffing algorithm for server-side reactive updates.

This module provides pure functions for comparing VDOM trees and generating
minimal update sequences. The diffing algorithm handles keyed reconciliation
similar to React's diffing algorithm.
"""

from typing import List, Dict, Any, Union, Optional
from .vdom import Node

# Type definitions
VDOM = Union[Node, str, int, bool, float]
VDOMUpdate = Dict[str, Any]
Path = List[int]


def diff_vdom(
    old_node: Optional[VDOM], new_node: Optional[VDOM], path: Path | None = None
) -> List[VDOMUpdate]:
    """
    Main VDOM diffing function that compares two VDOM trees and produces update operations.

    Args:
        old_node: The previous VDOM tree (or None for initial render)
        new_node: The new VDOM tree (or None for removal)
        path: Current path in the tree (list of child indices)

    Returns:
        List of update operations to transform old_node into new_node
    """
    if path is None:
        path = []

    operations = []

    # Handle null cases
    if old_node is None and new_node is None:
        return []
    elif old_node is None and new_node is not None:
        # Insert new node
        operations.append(
            {
                "type": "insert",
                "path": path,
                "data": {"node": _serialize_node(new_node)},
            }
        )
        return operations
    elif old_node is not None and new_node is None:
        # Remove old node
        operations.append({"type": "remove", "path": path})
        return operations

    # Both nodes exist - check if they're the same type
    old_is_element = isinstance(old_node, Node)
    new_is_element = isinstance(new_node, Node)

    # If types differ, replace entirely
    if old_is_element != new_is_element:
        operations.append(
            {
                "type": "replace",
                "path": path,
                "data": {"node": _serialize_node(new_node)},
            }
        )
        return operations

    # Handle text nodes (primitive values)
    if not old_is_element and not new_is_element:
        if old_node != new_node:
            operations.append(
                {"type": "replace", "path": path, "data": {"node": new_node}}
            )
        return operations

    # Both are Node instances - compare them
    old_element = old_node
    new_element = new_node

    # If tags differ, replace entirely
    if old_element.tag != new_element.tag:
        operations.append(
            {
                "type": "replace",
                "path": path,
                "data": {"node": _serialize_node(new_element)},
            }
        )
        return operations

    # Same tag - check props and children
    prop_operations = diff_props(old_element.props, new_element.props, path)
    operations.extend(prop_operations)

    # Diff children
    children_operations = diff_children(
        old_element.children, new_element.children, path
    )
    operations.extend(children_operations)

    return operations


def diff_props(
    old_props: Dict[str, Any], new_props: Dict[str, Any], path: Path
) -> List[VDOMUpdate]:
    """
    Compare properties of two nodes and generate update operations.

    Args:
        old_props: Previous properties
        new_props: New properties
        path: Path to the node

    Returns:
        List of property update operations
    """
    operations = []

    # Check if props actually changed
    if old_props == new_props:
        return operations

    # Find added/changed props
    changed_props = {}
    for key, value in new_props.items():
        if key not in old_props or old_props[key] != value:
            changed_props[key] = value

    # Find removed props
    removed_props = []
    for key in old_props:
        if key not in new_props:
            removed_props.append(key)

    # Generate update operation if there are changes
    if changed_props or removed_props:
        operation = {
            "type": "update_props",
            "path": path,
            "data": {"set": changed_props, "remove": removed_props},
        }
        operations.append(operation)

    return operations


def diff_children(
    old_children: List[VDOM], new_children: List[VDOM], path: Path
) -> List[VDOMUpdate]:
    """
    Compare children arrays and generate update operations.

    This implementation properly handles keyed reconciliation, similar to React's diffing algorithm.
    For keyed children, it identifies moves, inserts, and removes.
    For unkeyed children, it uses positional diffing.

    Args:
        old_children: Previous children array
        new_children: New children array
        path: Path to the parent node

    Returns:
        List of update operations for children
    """
    operations = []

    # Check if we have any keyed nodes to determine strategy
    has_keyed_old = any(
        isinstance(child, Node) and child.key is not None for child in old_children
    )
    has_keyed_new = any(
        isinstance(child, Node) and child.key is not None for child in new_children
    )

    if has_keyed_old or has_keyed_new:
        # Use keyed reconciliation
        operations.extend(_diff_keyed_children(old_children, new_children, path))
    else:
        # Use positional reconciliation
        operations.extend(_diff_positional_children(old_children, new_children, path))

    return operations


def _diff_keyed_children(
    old_children: List[VDOM], new_children: List[VDOM], path: Path
) -> List[VDOMUpdate]:
    """Handle keyed children reconciliation."""
    operations = []

    # Build maps of keyed elements
    old_keyed = {}
    old_positions = {}
    new_keyed = {}
    new_positions = {}

    for i, child in enumerate(old_children):
        if isinstance(child, Node) and child.key is not None:
            old_keyed[child.key] = child
            old_positions[child.key] = i

    for i, child in enumerate(new_children):
        if isinstance(child, Node) and child.key is not None:
            new_keyed[child.key] = child
            new_positions[child.key] = i

    # Track which old positions are still used
    used_old_positions = set()

    # Process new children in order
    for new_index, new_child in enumerate(new_children):
        child_path = path + [new_index]

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
                            "data": {"from": old_index, "to": new_index, "key": key},
                        }
                    )

                # Diff the moved/stayed element
                if old_child != new_child:
                    child_operations = diff_vdom(old_child, new_child, child_path)
                    operations.extend(child_operations)
            else:
                # New keyed element - insert
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": {"node": _serialize_node(new_child)},
                    }
                )
        else:
            # Unkeyed new element - try to match positionally with unkeyed old elements
            if (
                new_index < len(old_children)
                and new_index not in used_old_positions
                and not (
                    isinstance(old_children[new_index], Node)
                    and old_children[new_index].key is not None
                )
            ):
                # Both unkeyed at same position - diff them
                old_child = old_children[new_index]
                used_old_positions.add(new_index)

                if old_child != new_child:
                    # Different unkeyed elements - replace
                    operations.append(
                        {
                            "type": "replace",
                            "path": child_path,
                            "data": {"node": _serialize_node(new_child)},
                        }
                    )
            else:
                # No matching unkeyed element at this position - insert
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": {"node": _serialize_node(new_child)},
                    }
                )

    # Remove old keyed elements that are no longer present
    for key, old_child in old_keyed.items():
        if key not in new_keyed:
            old_index = old_positions[key]
            operations.append(
                {"type": "remove", "path": path + [old_index], "data": {"key": key}}
            )

    # Handle unkeyed old elements that weren't replaced
    for old_index, old_child in enumerate(old_children):
        if old_index not in used_old_positions and not (
            isinstance(old_child, Node) and old_child.key is not None
        ):
            operations.append({"type": "remove", "path": path + [old_index]})

    return operations


def _diff_positional_children(
    old_children: List[VDOM], new_children: List[VDOM], path: Path
) -> List[VDOMUpdate]:
    """Handle unkeyed children using positional diffing."""
    operations = []
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        child_path = path + [i]

        if i < len(old_children) and i < len(new_children):
            # Both exist - diff them
            old_child = old_children[i]
            new_child = new_children[i]
            child_operations = diff_vdom(old_child, new_child, child_path)
            operations.extend(child_operations)

        elif i < len(new_children):
            # New child - insert
            new_child = new_children[i]
            operations.append(
                {
                    "type": "insert",
                    "path": child_path,
                    "data": {"node": _serialize_node(new_child)},
                }
            )

        else:
            # Old child that's no longer present - remove
            operations.append({"type": "remove", "path": child_path})

    return operations


def _serialize_node(node: VDOM) -> Union[Dict[str, Any], str, int, bool, float]:
    """
    Serialize a VDOM node for inclusion in update operations.

    Args:
        node: The node to serialize

    Returns:
        Serialized representation suitable for JSON
    """
    if isinstance(node, Node):
        return node.to_dict()
    else:
        # Primitive value
        return node


def optimize_operations(operations: List[VDOMUpdate]) -> List[VDOMUpdate]:
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
        # Skip no-op property updates
        if (
            op["type"] == "update_props"
            and not op["data"]["set"]
            and not op["data"]["remove"]
        ):
            continue

        # For now, just include all other operations
        # Future optimizations could include:
        # - Merging consecutive property updates on the same path
        # - Removing operations that are immediately overwritten by replace operations
        # - Coalescing insert/remove pairs into replace operations
        optimized.append(op)

    return optimized
