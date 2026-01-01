"""
Test utilities for comparing VDOM trees and Node structures.
"""

from typing import Any

from pulse.transpiler.nodes import Element, Node, Primitive, PulseNode
from pulse.transpiler.vdom import VDOMElement, VDOMNode


def normalize_vdom_node(node: VDOMElement) -> dict[str, Any]:
	"""
	Normalize a VDOMElement by removing empty/None optional fields.

	This helps with comparison by ensuring semantically equivalent
	nodes compare as equal regardless of whether optional fields
	are missing, None, or empty.
	"""
	result: dict[str, Any] = {"tag": node["tag"]}
	if props := node.get("props"):
		result["props"] = props
	if children := node.get("children"):
		result["children"] = [normalize_vdom_tree(child) for child in children]
	if key := node.get("key"):
		result["key"] = key
	return result


def normalize_vdom_tree(
	tree: VDOMNode,
) -> dict[str, Any] | Primitive:
	"""
	Normalize a VDOM tree (VDOMNode or primitive) for comparison.
	"""
	if isinstance(tree, dict) and "tag" in tree:
		return normalize_vdom_node(tree)  # type: ignore[arg-type]
	else:
		# Primitive value or expression - return as-is
		return tree  # pyright: ignore[reportReturnType]


def normalize_node(node: Element) -> dict[str, Any]:
	"""
	Normalize a Node by converting it to a comparable dict format.
	"""
	result: dict[str, Any] = {"tag": node.tag}

	# Only include props if they exist and are non-empty
	if node.props:
		result["props"] = node.props

	# Only include children if they exist and are non-empty
	if node.children:
		result["children"] = [normalize_node_tree(child) for child in node.children]

	# Only include key if it exists and is not None
	if node.key is not None:
		result["key"] = node.key

	# Note: We don't include callbacks in comparison as they're functions

	return result


def normalize_node_tree(
	tree: Node,
) -> dict[str, Any] | Primitive:
	"""
	Normalize a Node tree (Node or primitive) for comparison.
	"""
	if isinstance(tree, PulseNode):
		raise NotImplementedError()
	return normalize_node(tree) if isinstance(tree, Element) else tree  # pyright: ignore[reportReturnType]


def assert_vdom_equal(actual: VDOMNode, expected: VDOMNode):
	"""
	Assert that two VDOM trees are semantically equal.

	This normalizes both trees before comparison to handle optional fields.
	"""
	normalized_actual = normalize_vdom_tree(actual)
	normalized_expected = normalize_vdom_tree(expected)

	assert normalized_actual == normalized_expected, (
		f"VDOM trees not equal:\nActual: {normalized_actual}\nExpected: {normalized_expected}"
	)


def assert_node_equal(actual: Node, expected: Node):
	"""
	Assert that two Node trees are semantically equal.

	This normalizes both trees before comparison to handle optional fields.
	"""
	normalized_actual = normalize_node_tree(actual)
	normalized_expected = normalize_node_tree(expected)

	assert normalized_actual == normalized_expected, (
		f"Node trees not equal:\nActual: {normalized_actual}\nExpected: {normalized_expected}"
	)
