"""Project Pulse UI trees into portable VDOM for the v5 encoder."""

from __future__ import annotations

from typing import cast

from pulse._serializer.types import PulseVDOM


def wrap_vdom(node: object) -> object:
	if type(node) is dict:
		return PulseVDOM(cast(dict[str, object], node))
	return node


def project_renderable(value: object) -> object | None:
	from pulse.renderer import snapshot_render
	from pulse.transpiler.nodes import Element, Expr, PulseNode, Value

	if isinstance(value, Value):
		return value.value
	if isinstance(value, (Element, PulseNode)):
		return wrap_vdom(snapshot_render(value))
	if isinstance(value, Expr):
		return wrap_vdom(value.render())
	return None
