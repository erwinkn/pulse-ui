from typing import (
    TypedDict,
    Union,
    Optional,
    Literal,
    Sequence,
    Any,
)
from .vdom import VDOM, Props, Node, PrimitiveNode, NodeTree


class InsertOperation(TypedDict):
    type: Literal["insert"]
    path: str
    data: VDOM


class RemoveOperation(TypedDict):
    type: Literal["remove"]
    path: str


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


def _render_to_vdom(node: Union[Node, PrimitiveNode], path: str) -> VDOM:
    if isinstance(node, Node):
        return node._render_node(path, {})
    return node


def _effective_props(node: Node, path: str) -> dict[str, Any]:
    props = dict(node.props or {})
    if node.callbacks:
        path_prefix = (path + ".") if path else ""
        for cb_name in node.callbacks.keys():
            props[cb_name] = f"$$fn:{path_prefix}{cb_name}"
    return props


def diff_node(
    old_node: Optional[Union[Node, PrimitiveNode]],
    new_node: Optional[Union[Node, PrimitiveNode]],
    path: str = "",
) -> list[VDOMOperation]:
    operations: list[VDOMOperation] = []

    # Handle null cases
    if old_node is None and new_node is None:
        return operations
    elif old_node is None:
        assert new_node is not None
        operations.append(
            {"type": "insert", "path": path, "data": _render_to_vdom(new_node, path)}
        )
        return operations
    elif new_node is None:
        operations.append({"type": "remove", "path": path, "data": None})
        return operations

    # Primitives equality
    if not isinstance(old_node, Node) and not isinstance(new_node, Node):
        if old_node == new_node:
            return operations
        else:
            operations.append({"type": "replace", "path": path, "data": new_node})
            return operations

    # Type mismatch or tag difference => replace
    if not isinstance(old_node, Node) or not isinstance(new_node, Node):
        operations.append(
            {"type": "replace", "path": path, "data": _render_to_vdom(new_node, path)}
        )
        return operations

    if old_node.tag != new_node.tag:
        operations.append(
            {"type": "replace", "path": path, "data": _render_to_vdom(new_node, path)}
        )
        return operations

    # Same tag - diff props (including callback placeholders)
    old_props = _effective_props(old_node, path)
    new_props = _effective_props(new_node, path)
    if old_props != new_props:
        operations.append({"type": "update_props", "path": path, "data": new_props})

    # Diff children
    old_children: list[NodeTree] = list(old_node.children or [])
    new_children: list[NodeTree] = list(new_node.children or [])

    # Determine strategy based on keys
    has_keyed_old = any(isinstance(c, Node) and c.key is not None for c in old_children)
    has_keyed_new = any(isinstance(c, Node) and c.key is not None for c in new_children)

    if has_keyed_old or has_keyed_new:
        operations.extend(_diff_keyed_children(old_children, new_children, path))
    else:
        operations.extend(_diff_positional_children(old_children, new_children, path))

    return operations


def _diff_keyed_children(
    old_children: Sequence[NodeTree], new_children: Sequence[NodeTree], path: str
) -> list[VDOMOperation]:
    operations: list[VDOMOperation] = []

    old_keyed: dict[str, Node] = {}
    old_positions: dict[str, int] = {}
    new_keyed: dict[str, Node] = {}

    for i, child in enumerate(old_children):
        if isinstance(child, Node) and child.key is not None:
            old_keyed[child.key] = child
            old_positions[child.key] = i

    for i, child in enumerate(new_children):
        if isinstance(child, Node) and child.key is not None:
            new_keyed[child.key] = child

    used_old_positions: set[int] = set()

    for new_index, new_child in enumerate(new_children):
        child_path = f"{path}.{new_index}" if path else str(new_index)

        if isinstance(new_child, Node) and new_child.key is not None:
            key = new_child.key
            if key in old_keyed:
                old_child = old_keyed[key]
                old_index = old_positions[key]
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
                used_old_positions.add(old_index)
                operations.extend(diff_node(old_child, new_child, child_path))
            else:
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": _render_to_vdom(new_child, child_path),
                    }
                )
        else:
            # Unkeyed new element - try positional match
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
                used_old_positions.add(new_index)
                operations.extend(
                    diff_node(old_children[new_index], new_child, child_path)
                )
            else:
                operations.append(
                    {
                        "type": "insert",
                        "path": child_path,
                        "data": _render_to_vdom(new_child, child_path),
                    }
                )

    # Remove old keyed elements that disappeared
    for key, old_child in old_keyed.items():
        if key not in new_keyed:
            old_index = old_positions[key]
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append({"type": "remove", "path": old_child_path, "data": key})

    # Remove leftover unkeyed olds
    for old_index, old_child in enumerate(old_children):
        if old_index not in used_old_positions and not (
            isinstance(old_child, Node) and old_child.key is not None
        ):
            old_child_path = f"{path}.{old_index}" if path else str(old_index)
            operations.append({"type": "remove", "path": old_child_path, "data": None})

    return operations


def _diff_positional_children(
    old_children: Sequence[NodeTree], new_children: Sequence[NodeTree], path: str
) -> list[VDOMOperation]:
    operations: list[VDOMOperation] = []
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        child_path = f"{path}.{i}" if path else str(i)
        old_child = old_children[i] if i < len(old_children) else None
        new_child = new_children[i] if i < len(new_children) else None

        if old_child is not None and new_child is not None:
            operations.extend(diff_node(old_child, new_child, child_path))
        elif new_child is not None:
            operations.append(
                {
                    "type": "insert",
                    "path": child_path,
                    "data": _render_to_vdom(new_child, child_path),
                }
            )
        else:
            operations.append({"type": "remove", "path": child_path, "data": None})

    return operations
