import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple, TypeAlias, cast

from pulse.helpers import values_equal
from pulse.transpiler.context import interpreted_mode
from pulse.transpiler.function import AnyJsFunction, JsFunction, JsFunctionCall
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import JSExpr, to_js_expr
from pulse.vdom import (
	VDOM,
	Callback,
	Callbacks,
	ComponentNode,
	Element,
	Node,
	PathDelta,
	Props,
	ReconciliationOperation,
	ReplaceOperation,
	UpdateCallbacksOperation,
	UpdateJsExprPathsOperation,
	UpdatePropsDelta,
	UpdatePropsOperation,
	UpdateRenderPropsOperation,
	VDOMNode,
	VDOMOperation,
)


def is_jsexpr(value: object) -> bool:
	"""Check if a value is a JSExpr, Import, JsFunction, or JsFunctionCall."""
	return isinstance(value, (JSExpr, Import, JsFunction, JsFunctionCall))


def emit_jsexpr(
	value: "JSExpr | Import | AnyJsFunction | JsFunctionCall[*tuple[Any, ...]]",
) -> str:
	"""Emit a JSExpr in interpreted mode (for client-side evaluation)."""
	with interpreted_mode():
		if isinstance(value, Import):
			return value.emit()
		if isinstance(value, JsFunction):
			# Emit as a function reference: get_object('fn_name')
			return f"get_object('{value.js_name}')"
		if isinstance(value, JsFunctionCall):
			# Emit as a function call: fn_name(arg1, arg2, ...)
			fn_name = f"get_object('{value.fn.js_name}')"
			args_js = ", ".join(to_js_expr(arg).emit() for arg in value.args)
			return f"{fn_name}({args_js})"
		return value.emit()


RenderPath: TypeAlias = str


class RenderTree:
	root: Element
	callbacks: Callbacks
	render_props: set[str]
	jsexpr_paths: set[str]  # paths containing JS expressions

	def __init__(self, root: Element) -> None:
		self.root = root
		self.callbacks = {}
		self.render_props = set()
		self.jsexpr_paths = set()
		self.normalized: Element | None = None

	def render(self) -> VDOM:
		renderer = Renderer()
		vdom, normalized = renderer.render_tree(self.root)
		self.root = normalized
		self.callbacks = renderer.callbacks
		self.render_props = renderer.render_props
		self.jsexpr_paths = renderer.jsexpr_paths
		self.normalized = normalized
		return vdom

	def diff(self, new_tree: Element) -> list[VDOMOperation]:
		if self.normalized is None:
			raise RuntimeError("RenderTree.render must be called before diff")

		renderer = Renderer()
		normalized = renderer.reconcile_tree(self.normalized, new_tree, path="")

		callback_prev = set(self.callbacks.keys())
		callback_next = set(renderer.callbacks.keys())
		callback_add = sorted(callback_next - callback_prev)
		callback_remove = sorted(callback_prev - callback_next)

		render_props_prev = self.render_props
		render_props_next = renderer.render_props
		render_props_add = sorted(render_props_next - render_props_prev)
		render_props_remove = sorted(render_props_prev - render_props_next)

		prefix: list[VDOMOperation] = []

		if callback_add or callback_remove:
			callback_delta: PathDelta = {}
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
			render_props_delta: PathDelta = {}
			if render_props_add:
				render_props_delta["add"] = render_props_add
			if render_props_remove:
				render_props_delta["remove"] = render_props_remove
			prefix.append(
				UpdateRenderPropsOperation(
					type="update_render_props", path="", data=render_props_delta
				)
			)

		jsexpr_prev = self.jsexpr_paths
		jsexpr_next = renderer.jsexpr_paths
		jsexpr_add = sorted(jsexpr_next - jsexpr_prev)
		jsexpr_remove = sorted(jsexpr_prev - jsexpr_next)
		if jsexpr_add or jsexpr_remove:
			jsexpr_delta: PathDelta = {}
			if jsexpr_add:
				jsexpr_delta["add"] = jsexpr_add
			if jsexpr_remove:
				jsexpr_delta["remove"] = jsexpr_remove
			prefix.append(
				UpdateJsExprPathsOperation(
					type="update_jsexpr_paths", path="", data=jsexpr_delta
				)
			)

		ops = prefix + renderer.operations if prefix else renderer.operations

		self.callbacks = renderer.callbacks
		self.render_props = renderer.render_props
		self.jsexpr_paths = renderer.jsexpr_paths
		self.normalized = normalized
		self.root = normalized

		return ops

	def unmount(self) -> None:
		if self.normalized is not None:
			unmount_element(self.normalized)
			self.normalized = None
		self.callbacks.clear()
		self.render_props.clear()
		self.jsexpr_paths.clear()


# Prefix for JSExpr values - code is embedded after the colon
JSEXPR_PREFIX = "$js:"


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
		self.jsexpr_paths: set[str] = set()
		self.operations: list[VDOMOperation] = []

	# ------------------------------------------------------------------
	# Rendering helpers
	# ------------------------------------------------------------------

	def render_tree(self, node: Element, path: RenderPath = "") -> tuple[VDOM, Element]:
		if isinstance(node, ComponentNode):
			return self.render_component(node, path)
		if isinstance(node, Node):
			return self.render_node(node, path)
		# Handle JSExpr as children - emit JS code with $js: prefix
		if is_jsexpr(node):
			# Safe cast: is_jsexpr() ensures node is JSExpr | Import | JsFunctionCall
			node_as_jsexpr = cast(
				"JSExpr | Import | JsFunctionCall[*tuple[Any, ...]]", cast(object, node)
			)
			js_code = emit_jsexpr(node_as_jsexpr)
			self.jsexpr_paths.add(path)
			return f"{JSEXPR_PREFIX}{js_code}", cast(Element, node)
		return node, node

	def render_component(
		self, component: ComponentNode, path: RenderPath
	) -> tuple[VDOM, ComponentNode]:
		with component.hooks:
			rendered = component.fn(*component.args, **component.kwargs)
		vdom, normalized_child = self.render_tree(rendered, path)
		component.contents = normalized_child
		return vdom, component

	def render_node(self, element: Node, path: RenderPath) -> tuple[VDOMNode, Node]:
		vdom_node: VDOMNode = {"tag": element.tag}
		if element.key is not None:
			vdom_node["key"] = element.key

		props = element.props or {}
		props_result = self.diff_props({}, props, path)
		if props_result.delta_set:
			vdom_node["props"] = props_result.delta_set

		for task in props_result.render_prop_reconciles:
			normalized_value = self.reconcile_tree(
				task.previous, task.current, task.path
			)
			props_result.normalized[task.key] = normalized_value

		element.props = props_result.normalized or None

		children_vdom: list[VDOM] = []
		normalized_children: list[Element] = []
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
		previous: Element,
		current: Element,
		path: RenderPath = "",
	) -> Element:
		if not same_node(previous, current):
			unmount_element(previous)
			new_vdom, normalized = self.render_tree(current, path)
			self.operations.append(
				ReplaceOperation(type="replace", path=path, data=new_vdom)
			)
			return normalized

		if isinstance(previous, ComponentNode) and isinstance(current, ComponentNode):
			return self.reconcile_component(previous, current, path)

		if isinstance(previous, Node) and isinstance(current, Node):
			return self.reconcile_element(previous, current, path)

		return current

	def reconcile_component(
		self,
		previous: ComponentNode,
		current: ComponentNode,
		path: RenderPath,
	) -> ComponentNode:
		current.hooks = previous.hooks
		current.contents = previous.contents

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
		previous: Node,
		current: Node,
		path: RenderPath,
	) -> Node:
		prev_props = previous.props or {}
		new_props = current.props or {}
		props_result = self.diff_props(prev_props, new_props, path)

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
				task.previous, task.current, task.path
			)
			props_result.normalized[task.key] = normalized_value

		prev_children = normalize_children(previous.children)
		next_children = normalize_children(current.children)
		normalized_children = self.reconcile_children(
			prev_children, next_children, path
		)

		# Mutate the current node to avoid allocations
		current.props = props_result.normalized or None
		current.children = normalized_children
		return current

	def reconcile_children(
		self,
		c1: list[Element],
		c2: list[Element],
		path: RenderPath,
	) -> list[Element]:
		if not c1 and not c2:
			return []

		N1 = len(c1)
		N2 = len(c2)
		norm: list[Element] = [None] * N2
		N = min(N1, N2)
		i = 0
		# Fast path: if elements haven't changed, perform a single pass
		while i < N:
			x1 = c1[i]
			x2 = c2[i]
			if not same_node(x1, x2):
				break  # enter keyed reconciliation
			norm[i] = self.reconcile_tree(x1, x2, join_path(path, i))
			i += 1

		# Exits if previous and current children lists are of the same size and
		# the previous loop did not break. Also works for empty lists.
		if i == N1 == N2:
			return norm

		# Enter keyed reconciliation. We emit the reconciliation op in advance,
		# as further ops will use the post-reconciliation paths.
		op = ReconciliationOperation(
			type="reconciliation", path=path, N=len(c2), new=([], []), reuse=([], [])
		)
		self.operations.append(op)

		# Build key index
		keys_to_old_idx: dict[str, int] = {}
		for j1 in range(i, N1):
			if key := getattr(c1[j1], "key", None):
				keys_to_old_idx[key] = j1

		# Build the reconciliation instructions
		reused = [False] * (N1 - i)
		for j2 in range(i, N2):
			x2 = c2[j2]
			# Case 1: this is a keyed node, try to reuse it if it already existed
			k = getattr(x2, "key", None)
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
			# Case 2: try to reuse the node at the same position
			if not k and j2 < N1:
				x1 = c1[j2]
				if same_node(x1, x2):
					reused[j2 - i] = True
					norm[j2] = self.reconcile_tree(x1, x2, join_path(path, j2))
					continue

			# Case 3: this is a new node, render it at the new path
			vdom, el = self.render_tree(x2, join_path(path, j2))
			op["new"][0].append(j2)
			op["new"][1].append(vdom)
			norm[j2] = el

		# Unmount old nodes we haven't reused
		for j1 in range(i, N1):
			if not reused[j1 - i]:
				self.unmount_subtree(c1[j1])

		return norm

	# ------------------------------------------------------------------
	# Prop diffing
	# ------------------------------------------------------------------

	def diff_props(
		self,
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

			if is_jsexpr(value):
				if isinstance(old_value, (Node, ComponentNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				# Emit the JSExpr with $js: prefix - code is embedded in the value
				js_code = emit_jsexpr(cast("JSExpr | Import", value))
				self.jsexpr_paths.add(prop_path)
				js_value = f"{JSEXPR_PREFIX}{js_code}"
				old_js_code = (
					emit_jsexpr(cast("JSExpr | Import", old_value))
					if is_jsexpr(old_value)
					else None
				)
				if old_js_code != js_code:
					updated[key] = js_value
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
					vdom_value, normalized_value = self.render_tree(value, prop_path)
					normalized[key] = normalized_value
					updated[key] = vdom_value
				continue

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
