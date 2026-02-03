from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import NoneType
from typing import Any, NamedTuple, TypeAlias, cast

from pulse.context import PulseContext
from pulse.debounce import Debounced
from pulse.helpers import values_equal
from pulse.hooks.core import HookContext
from pulse.refs import Ref
from pulse.transpiler import Import
from pulse.transpiler.function import Constant, JsFunction, JsxFunction
from pulse.transpiler.nodes import (
	Child,
	Children,
	Element,
	Expr,
	Literal,
	Node,
	PulseNode,
	Value,
)
from pulse.transpiler.vdom import (
	VDOM,
	ReconciliationOperation,
	RegistryRef,
	ReplaceOperation,
	UpdatePropsDelta,
	UpdatePropsOperation,
	VDOMElement,
	VDOMNode,
	VDOMOperation,
	VDOMPropValue,
)

PropValue: TypeAlias = Node | Callable[..., Any] | Debounced[Any, Any] | Ref[Any]

FRAGMENT_TAG = ""
MOUNT_PREFIX = "$$"
CALLBACK_PLACEHOLDER = "$cb"


class Callback(NamedTuple):
	fn: Callable[..., Any]
	n_args: int


Callbacks = dict[str, Callback]


@dataclass(slots=True)
class DiffPropsResult:
	normalized: dict[str, PropValue]
	delta_set: dict[str, VDOMPropValue]
	delta_remove: set[str]
	render_prop_reconciles: list["RenderPropTask"]
	eval_keys: set[str]
	eval_changed: bool


class RenderPropTask(NamedTuple):
	key: str
	previous: Element | PulseNode
	current: Element | PulseNode
	path: str


class RenderTree:
	element: Node
	callbacks: Callbacks
	rendered: bool

	def __init__(self, element: Node) -> None:
		self.element = element
		self.callbacks = {}
		self.rendered = False

	def render(self) -> VDOM:
		"""First render. Returns VDOM."""
		renderer = Renderer()
		vdom, self.element = renderer.render_tree(self.element)
		self.callbacks = renderer.callbacks
		self.rendered = True
		return vdom

	def rerender(self, new_element: Node | None = None) -> list[VDOMOperation]:
		"""Re-render and return update operations.

		If new_element is provided, reconciles against it (for testing).
		Otherwise, reconciles against the current element (production use).
		"""
		if not self.rendered:
			raise RuntimeError("render() must be called before rerender()")
		target = new_element if new_element is not None else self.element
		renderer = Renderer()
		self.element = renderer.reconcile_tree(self.element, target, path="")
		self.callbacks = renderer.callbacks
		return renderer.operations

	def unmount(self) -> None:
		if self.rendered:
			unmount_element(self.element)
			self.rendered = False
		self.callbacks.clear()


class Renderer:
	def __init__(self) -> None:
		self.callbacks: Callbacks = {}
		self.operations: list[VDOMOperation] = []

	# ------------------------------------------------------------------
	# Rendering helpers
	# ------------------------------------------------------------------

	def render_tree(self, node: Node, path: str = "") -> tuple[Any, Node]:
		if isinstance(node, PulseNode):
			return self.render_component(node, path)
		if isinstance(node, Element):
			return self.render_node(node, path)
		if isinstance(node, Value):
			return node.value, node.value
		if isinstance(node, Expr):
			return node.render(), node
		# Pass through any other value - serializer will validate
		return node, node

	def render_component(
		self, component: PulseNode, path: str
	) -> tuple[VDOM, PulseNode]:
		if component.hooks is None:
			component.hooks = HookContext()
		with component.hooks:
			rendered = component.fn(*component.args, **component.kwargs)
		vdom, normalized_child = self.render_tree(rendered, path)
		component.contents = normalized_child
		return vdom, component

	def render_node(self, element: Element, path: str) -> tuple[VDOMNode, Element]:
		tag = self.render_tag(element.tag)
		vdom_node: VDOMElement = {"tag": tag}
		if (key_val := key_value(element)) is not None:
			vdom_node["key"] = key_val

		props = element.props_dict()
		props_result = self.diff_props({}, props, path, prev_eval=set())
		if props_result.delta_set:
			vdom_node["props"] = props_result.delta_set
		if props_result.eval_keys:
			vdom_node["eval"] = sorted(props_result.eval_keys)

		for task in props_result.render_prop_reconciles:
			normalized_value = self.reconcile_tree(
				task.previous, task.current, task.path
			)
			props_result.normalized[task.key] = normalized_value

		element.props = props_result.normalized or None

		children_vdom: list[VDOM] = []
		normalized_children: list[Node] = []
		for idx, child in enumerate(normalize_children(element.children)):
			child_path = join_path(path, idx)
			child_vdom, normalized_child = self.render_tree(child, child_path)
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
		previous: Node,
		current: Node,
		path: str = "",
	) -> Node:
		if isinstance(current, Value):
			current = current.value
		if isinstance(previous, Value):
			previous = previous.value
		if not same_node(previous, current):
			unmount_element(previous)
			new_vdom, normalized = self.render_tree(current, path)
			self.operations.append(
				ReplaceOperation(type="replace", path=path, data=new_vdom)
			)
			return normalized

		if isinstance(previous, PulseNode) and isinstance(current, PulseNode):
			return self.reconcile_component(previous, current, path)

		if isinstance(previous, Element) and isinstance(current, Element):
			return self.reconcile_element(previous, current, path)

		return current

	def reconcile_component(
		self,
		previous: PulseNode,
		current: PulseNode,
		path: str,
	) -> PulseNode:
		current.hooks = previous.hooks
		current.contents = previous.contents

		if current.hooks is None:
			current.hooks = HookContext()

		with current.hooks:
			rendered = current.fn(*current.args, **current.kwargs)

		if current.contents is None:
			new_vdom, normalized = self.render_tree(rendered, path)
			current.contents = normalized
			self.operations.append(
				ReplaceOperation(type="replace", path=path, data=new_vdom)
			)
		else:
			current.contents = self.reconcile_tree(current.contents, rendered, path)

		return current

	def reconcile_element(
		self,
		previous: Element,
		current: Element,
		path: str,
	) -> Element:
		prev_props = previous.props_dict()
		new_props = current.props_dict()
		prev_eval = eval_keys_for_props(prev_props)
		props_result = self.diff_props(prev_props, new_props, path, prev_eval)

		if (
			props_result.delta_set
			or props_result.delta_remove
			or props_result.eval_changed
		):
			delta: UpdatePropsDelta = {}
			if props_result.delta_set:
				delta["set"] = props_result.delta_set
			if props_result.delta_remove:
				delta["remove"] = sorted(props_result.delta_remove)
			if props_result.eval_changed:
				delta["eval"] = sorted(props_result.eval_keys)
			self.operations.append(
				UpdatePropsOperation(type="update_props", path=path, data=delta)
			)

		for task in props_result.render_prop_reconciles:
			normalized_value = self.reconcile_tree(
				task.previous, task.current, task.path
			)
			props_result.normalized[task.key] = normalized_value

		prev_children = normalize_children(previous.children)
		next_children = normalize_children(current.children)
		normalized_children = self.reconcile_children(
			prev_children, next_children, path
		)

		current.props = props_result.normalized or None
		current.children = normalized_children
		return current

	def reconcile_children(
		self,
		c1: list[Node],
		c2: list[Node],
		path: str,
	) -> list[Node]:
		if not c1 and not c2:
			return []

		N1 = len(c1)
		N2 = len(c2)
		norm: list[Node | None] = [None] * N2
		N = min(N1, N2)
		i = 0
		while i < N:
			x1 = c1[i]
			x2 = c2[i]
			if not same_node(x1, x2):
				break
			norm[i] = self.reconcile_tree(x1, x2, join_path(path, i))
			i += 1

		if i == N1 == N2:
			return norm

		op = ReconciliationOperation(
			type="reconciliation", path=path, N=len(c2), new=([], []), reuse=([], [])
		)
		self.operations.append(op)

		keys_to_old_idx: dict[str, int] = {}
		for j1 in range(i, N1):
			key = key_value(c1[j1])
			if key is not None:
				keys_to_old_idx[key] = j1

		reused = [False] * (N1 - i)
		for j2 in range(i, N2):
			x2 = c2[j2]
			k = key_value(x2)
			if k is not None:
				j1 = keys_to_old_idx.get(k)
				if j1 is not None:
					x1 = c1[j1]
					if same_node(x1, x2):
						norm[j2] = self.reconcile_tree(x1, x2, join_path(path, j2))
						reused[j1 - i] = True
						if j1 != j2:
							op["reuse"][0].append(j2)
							op["reuse"][1].append(j1)
						continue
			if k is None and j2 < N1:
				x1 = c1[j2]
				if same_node(x1, x2):
					reused[j2 - i] = True
					norm[j2] = self.reconcile_tree(x1, x2, join_path(path, j2))
					continue

			vdom, el = self.render_tree(x2, join_path(path, j2))
			op["new"][0].append(j2)
			op["new"][1].append(vdom)
			norm[j2] = el

		for j1 in range(i, N1):
			if not reused[j1 - i]:
				self.unmount_subtree(c1[j1])

		return norm

	# ------------------------------------------------------------------
	# Prop diffing
	# ------------------------------------------------------------------

	def diff_props(
		self,
		previous: dict[str, PropValue],
		current: dict[str, PropValue],
		path: str,
		prev_eval: set[str],
	) -> DiffPropsResult:
		updated: dict[str, VDOMPropValue] = {}
		normalized: dict[str, PropValue] | None = None
		render_prop_tasks: list[RenderPropTask] = []
		eval_keys: set[str] = set()
		removed_keys = set(previous.keys()) - set(current.keys())

		for key, value in current.items():
			old_value = previous.get(key)
			prop_path = join_path(path, key)

			if isinstance(value, (Element, PulseNode)):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					if normalized is None:
						normalized = current.copy()
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
					vdom_value, normalized_value = self.render_tree(value, prop_path)
					if normalized is None:
						normalized = current.copy()
					normalized[key] = normalized_value
					updated[key] = cast(VDOMPropValue, vdom_value)
				continue

			if isinstance(value, Value):
				unwrapped = value.value
				if normalized is None:
					normalized = current.copy()
				normalized[key] = unwrapped
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if key not in previous or not values_equal(unwrapped, old_value):
					updated[key] = cast(VDOMPropValue, unwrapped)
				continue

			if isinstance(value, Expr):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				if not (isinstance(old_value, Expr) and values_equal(old_value, value)):
					updated[key] = value.render()
				continue

			if key == "ref" and callable(value) and not isinstance(value, Ref):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				if isinstance(old_value, Ref):
					handle = old_value
				else:
					ctx = PulseContext.get()
					if ctx.render is None:
						raise RuntimeError("ref() requires an active render session")
					handle = Ref(ctx.render.get_ref_channel(), owns_channel=False)
				handle.bind_callback(value)
				normalized[key] = handle
				if not (isinstance(old_value, Ref) and values_equal(old_value, handle)):
					updated[key] = {
						"__pulse_ref__": {
							"channelId": handle.channel_id,
							"refId": handle.id,
						}
					}
				continue

			if isinstance(value, Ref):
				if key != "ref":
					raise TypeError("Ref can only be used as the 'ref' prop")
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				if not (isinstance(old_value, Ref) and values_equal(old_value, value)):
					updated[key] = {
						"__pulse_ref__": {
							"channelId": value.channel_id,
							"refId": value.id,
						}
					}
				continue
			if isinstance(value, Debounced):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				register_callback(self.callbacks, prop_path, value.fn)
				prev_delay = (
					old_value.delay_ms if isinstance(old_value, Debounced) else None
				)
				if prev_delay != value.delay_ms:
					updated[key] = format_callback_placeholder(value.delay_ms)
				continue

			if callable(value):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				register_callback(self.callbacks, prop_path, value)
				if not callable(old_value) or isinstance(old_value, Debounced):
					updated[key] = CALLBACK_PLACEHOLDER
				continue

			if isinstance(old_value, (Element, PulseNode)):
				unmount_element(old_value)
			# No normalization needed - value passes through unchanged
			if key not in previous or not values_equal(value, old_value):
				updated[key] = cast(VDOMPropValue, value)

		for key in removed_keys:
			old_value = previous.get(key)
			if isinstance(old_value, (Element, PulseNode)):
				unmount_element(old_value)

		normalized_props = normalized if normalized is not None else current.copy()
		eval_changed = eval_keys != prev_eval
		return DiffPropsResult(
			normalized=normalized_props,
			delta_set=updated,
			delta_remove=removed_keys,
			render_prop_reconciles=render_prop_tasks,
			eval_keys=eval_keys,
			eval_changed=eval_changed,
		)

	# ------------------------------------------------------------------
	# Expression + tag rendering
	# ------------------------------------------------------------------

	def render_tag(self, tag: str | Expr):
		if isinstance(tag, str):
			return tag

		return self.register_component_expr(tag)

	def register_component_expr(self, expr: Expr):
		ref = registry_ref(expr)
		if ref is not None:
			return f"{MOUNT_PREFIX}{ref['key']}"
		tag = expr.render()
		if isinstance(tag, (int, float, bool, NoneType)):
			raise TypeError(f"Invalid element tag: {tag}")
		return tag

	# ------------------------------------------------------------------
	# Unmount helper
	# ------------------------------------------------------------------

	def unmount_subtree(self, node: Node) -> None:
		unmount_element(node)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def registry_ref(expr: Expr) -> RegistryRef | None:
	if isinstance(expr, (Import, JsFunction, Constant, JsxFunction)):
		return {"t": "ref", "key": expr.id}
	return None


def prop_requires_eval(value: PropValue) -> bool:
	if isinstance(value, Value):
		return False
	if isinstance(value, (Element, PulseNode)):
		return True
	if isinstance(value, Expr):
		return True
	if isinstance(value, Ref):
		return True
	if isinstance(value, Debounced):
		return True
	return callable(value)


def eval_keys_for_props(props: dict[str, PropValue]) -> set[str]:
	eval_keys: set[str] = set()
	for key, value in props.items():
		if prop_requires_eval(value):
			eval_keys.add(key)
	return eval_keys


def normalize_children(children: Children | None) -> list[Node]:
	if not children:
		return []

	out: list[Node] = []
	seen_keys: set[str] = set()

	def register_key(item: Node) -> None:
		key: str | None = None
		if isinstance(item, PulseNode):
			key = item.key
		elif isinstance(item, Element):
			key = key_value(item)
		if key is None:
			return
		if key in seen_keys:
			raise ValueError(f"Duplicate key '{key}'")
		seen_keys.add(key)

	def visit(item: Child) -> None:
		if isinstance(item, dict):
			raise TypeError("Dict is not a valid child; wrap in Value for props")
		if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
			for sub in item:
				visit(sub)
		else:
			node = cast(Node, item)
			register_key(node)
			out.append(node)

	for child in children:
		visit(child)

	return out


def format_callback_placeholder(delay_ms: float | None) -> str:
	if delay_ms is None:
		return CALLBACK_PLACEHOLDER
	if delay_ms.is_integer():
		suffix = str(int(delay_ms))
	else:
		suffix = format(delay_ms, "g")
	return f"{CALLBACK_PLACEHOLDER}:{suffix}"


def register_callback(
	callbacks: Callbacks,
	path: str,
	fn: Callable[..., Any],
) -> None:
	n_args = len(inspect.signature(fn).parameters)
	callbacks[path] = Callback(fn=fn, n_args=n_args)


def join_path(prefix: str, path: str | int) -> str:
	if prefix:
		return f"{prefix}.{path}"
	return str(path)


def same_node(left: Node, right: Node) -> bool:
	if values_equal(left, right):
		return True
	if isinstance(left, Element) and isinstance(right, Element):
		return values_equal(left.tag, right.tag) and key_value(left) == key_value(right)
	if isinstance(left, PulseNode) and isinstance(right, PulseNode):
		return left.fn == right.fn and key_value(left) == key_value(right)
	return False


def key_value(node: Node | Node) -> str | None:
	key = getattr(node, "key", None)
	if isinstance(key, Literal):
		if not isinstance(key.value, str):
			raise TypeError("Element key must be a string")
		return key.value
	return cast(str | None, key)


def unmount_element(element: Node) -> None:
	if isinstance(element, PulseNode):
		if element.contents is not None:
			unmount_element(element.contents)
			element.contents = None
		if element.hooks is not None:
			element.hooks.unmount()
		return

	if isinstance(element, Element):
		props = element.props_dict()
		for value in props.values():
			if isinstance(value, (Element, PulseNode)):
				unmount_element(value)
		for child in normalize_children(element.children):
			unmount_element(child)
		element.children = []
		return
