"""Typed JSON VDOM format for transpiler_v2.

This module defines the JSON-serializable format produced by the v2 renderer.

Key goals:
- The VDOM tree is rebuilt into React elements on the client.
- Any embedded expression tree is evaluated on the client.
- Only nodes representable in this JSON format are renderable.

Notes:
- This is a *wire format* (JSON). It is intentionally more restrictive than the
  Python-side node graph in `pulse.transpiler_v2.nodes`.
- Server-side-only nodes (e.g. `PulseNode`, `Transformer`, statement nodes) must
  be rejected during rendering.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypeAlias, TypedDict

# =============================================================================
# JSON atoms
# =============================================================================

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


# =============================================================================
# Expression tree (client-evaluable)
# =============================================================================

# The expression format is a small tagged-union.
#
# - The client should treat these nodes as *pure*, deterministic expressions.
# - Identifiers should generally be avoided unless the client runtime provides
#   them (e.g. `Math`). Prefer `RegistryRef` for server-provided values.


class RegistryRef(TypedDict):
	"""Reference to an entry in the unified client registry."""

	t: Literal["ref"]
	key: str


class IdentifierExpr(TypedDict):
	t: Literal["id"]
	name: str


class LiteralExpr(TypedDict):
	t: Literal["lit"]
	value: JsonPrimitive


class UndefinedExpr(TypedDict):
	t: Literal["undef"]


class ArrayExpr(TypedDict):
	t: Literal["array"]
	items: list[VDOMExpr]


class ObjectExpr(TypedDict):
	t: Literal["object"]
	props: dict[str, VDOMExpr]


class MemberExpr(TypedDict):
	t: Literal["member"]
	obj: VDOMExpr
	prop: str


class SubscriptExpr(TypedDict):
	t: Literal["sub"]
	obj: VDOMExpr
	key: VDOMExpr


class CallExpr(TypedDict):
	t: Literal["call"]
	callee: VDOMExpr
	args: list[VDOMExpr]


class UnaryExpr(TypedDict):
	t: Literal["unary"]
	op: str
	arg: VDOMExpr


class BinaryExpr(TypedDict):
	t: Literal["binary"]
	op: str
	left: VDOMExpr
	right: VDOMExpr


class TernaryExpr(TypedDict):
	t: Literal["ternary"]
	cond: VDOMExpr
	then: VDOMExpr
	else_: VDOMExpr


class TemplateExpr(TypedDict):
	"""Template literal parts.

	Parts alternate: [str, expr, str, expr, str, ...].
	Always starts and ends with a string segment (may be empty).
	"""

	t: Literal["template"]
	parts: list[str | VDOMExpr]


class ArrowExpr(TypedDict):
	t: Literal["arrow"]
	params: list[str]
	body: VDOMExpr


class NewExpr(TypedDict):
	t: Literal["new"]
	ctor: VDOMExpr
	args: list[VDOMExpr]


VDOMExpr: TypeAlias = (
	RegistryRef
	| IdentifierExpr
	| LiteralExpr
	| UndefinedExpr
	| ArrayExpr
	| ObjectExpr
	| MemberExpr
	| SubscriptExpr
	| CallExpr
	| UnaryExpr
	| BinaryExpr
	| TernaryExpr
	| TemplateExpr
	| ArrowExpr
	| NewExpr
)


# =============================================================================
# VDOM tree (React element reconstruction)
# =============================================================================

CallbackPlaceholder: TypeAlias = Literal["$cb"]
"""Callback placeholder value.

The callback invocation target is derived from the element path + prop name.
Because the prop name is known from `VDOMElement.eval`, the placeholder can be a
single sentinel string.
"""


VDOMPropValue: TypeAlias = JsonValue | VDOMExpr | "VDOMElement" | CallbackPlaceholder
"""Allowed prop value types.

Hot path:
- If `VDOMElement.eval` is absent, props MUST be plain JSON (JsonValue).
- If `VDOMElement.eval` is present, only the listed prop keys may contain
  non-JSON values (VDOMExpr / VDOMElement / "$cb:...").
"""


class VDOMElement(TypedDict):
	"""A React element in wire format.

	Special tags:
	- "$$fragment": React Fragment
	- "$$<ComponentKey>": mount point for client component registry
	"""

	tag: str
	key: NotRequired[str]
	# Default: plain JSON props (no interpretation).
	# When `eval` is present, listed keys may contain VDOMExpr / VDOMElement / "$cb:...".
	props: NotRequired[dict[str, VDOMPropValue]]
	children: NotRequired[list["VDOMNode"]]
	# Marks which prop keys should be interpreted (evaluate expr / render node / bind callback).
	# The interpreter determines the action by inspecting the value shape:
	# - dict with "t": VDOMExpr
	# - dict with "tag": VDOMElement (render-prop subtree)
	# - "$cb": callback placeholder
	eval: NotRequired[list[str]]


VDOMPrimitive: TypeAlias = JsonPrimitive

# A node is either a primitive, an element, or an expression node.
VDOMNode: TypeAlias = VDOMPrimitive | VDOMElement | VDOMExpr

VDOM: TypeAlias = VDOMNode


# =============================================================================
# Update operations (reconciliation output)
# =============================================================================

RenderPath: TypeAlias = str


class ReplaceOperation(TypedDict):
	type: Literal["replace"]
	path: RenderPath
	data: VDOM


class ReconciliationOperation(TypedDict):
	type: Literal["reconciliation"]
	path: RenderPath
	N: int
	new: tuple[list[int], list[VDOM]]
	reuse: tuple[list[int], list[int]]


class UpdatePropsDelta(TypedDict, total=False):
	# Prop deltas only affect `element.props`.
	# If the element has `eval`, only those keys may use non-JSON values.
	set: dict[str, VDOMPropValue]
	remove: list[str]
	# Optional eval key list replacement for this element.
	# - If present, replaces `element.eval` entirely.
	# - Use [] to clear the eval list.
	eval: list[str]


class UpdatePropsOperation(TypedDict):
	type: Literal["update_props"]
	path: RenderPath
	data: UpdatePropsDelta


VDOMOperation: TypeAlias = (
	ReplaceOperation | UpdatePropsOperation | ReconciliationOperation
)


# =============================================================================
# View payload (initial render)
# =============================================================================


class PrerenderView(TypedDict):
	"""Minimal payload required by the client to render + apply updates."""

	vdom: VDOM
	# Optional shared registry (client components, constants, etc.)
	registry: NotRequired[dict[str, Any]]
