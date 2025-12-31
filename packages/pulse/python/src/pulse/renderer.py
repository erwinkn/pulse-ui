from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple, TypeAlias, cast

from pulse.helpers import values_equal
from pulse.hooks.core import HookContext
from pulse.transpiler_v2 import Import
from pulse.transpiler_v2.function import Constant, JsFunction, JsxFunction
from pulse.transpiler_v2.nodes import (
	Element,
	Expr,
	Literal,
	Primitive,
	PulseNode,
	Value,
)
from pulse.transpiler_v2.vdom import (
	VDOM,
	JsonPrimitive,
	JsonValue,
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

RenderPath: TypeAlias = str
RenderInput: TypeAlias = Primitive | Expr | PulseNode
NormalizedNode: TypeAlias = PulseNode | Expr | JsonValue
JsonCoercible: TypeAlias = (
	JsonPrimitive
	| list["JsonCoercible"]
	| tuple["JsonCoercible", ...]
	| dict[str, "JsonCoercible"]
)
CallbackFn: TypeAlias = Callable[..., Any]
PropInput: TypeAlias = JsonCoercible | Expr | Element | PulseNode | CallbackFn
NormalizedPropValue: TypeAlias = JsonValue | Expr | Element | PulseNode | CallbackFn
ChildInput: TypeAlias = NormalizedNode | Iterable["ChildInput"]

FRAGMENT_TAG = ""
MOUNT_PREFIX = "$$"
CALLBACK_PLACEHOLDER = "$cb"


class Callback(NamedTuple):
	fn: CallbackFn
	n_args: int


Callbacks = dict[str, Callback]


@dataclass(slots=True)
class DiffPropsResult:
	normalized: dict[str, NormalizedPropValue]
	delta_set: dict[str, VDOMPropValue]
	delta_remove: set[str]
	render_prop_reconciles: list["RenderPropTask"]
	eval_keys: set[str]
	eval_changed: bool


class RenderPropTask(NamedTuple):
	key: str
	previous: Element | PulseNode
	current: Element | PulseNode
	path: RenderPath


class RenderTree:
	root: RenderInput
	callbacks: Callbacks
	operations: list[VDOMOperation]
	_normalized: NormalizedNode | None

	def __init__(self, root: RenderInput) -> None:
		self.root = root
		self.callbacks = {}
		self.operations = []
		self._normalized = None

	def render(self) -> VDOM:
		renderer = Renderer()
		vdom, normalized = renderer.render_tree(self.root)
		self.root = normalized
		self.callbacks = renderer.callbacks
		self._normalized = normalized
		return vdom

	def diff(self, new_tree: RenderInput) -> list[VDOMOperation]:
		if self._normalized is None:
			raise RuntimeError("RenderTree.render must be called before diff")

		renderer = Renderer()
		normalized = renderer.reconcile_tree(self._normalized, new_tree, path="")

		self.callbacks = renderer.callbacks
		self._normalized = normalized
		self.root = normalized

		return renderer.operations

	def unmount(self) -> None:
		if self._normalized is not None:
			unmount_element(self._normalized)
			self._normalized = None
		self.callbacks.clear()

	@property
	def normalized(self) -> NormalizedNode | None:
		return self._normalized


class Renderer:
	def __init__(self) -> None:
		self.callbacks: Callbacks = {}
		self.operations: list[VDOMOperation] = []

	# ------------------------------------------------------------------
	# Rendering helpers
	# ------------------------------------------------------------------

	def render_tree(
		self, node: RenderInput, path: RenderPath = ""
	) -> tuple[VDOM, NormalizedNode]:
		if isinstance(node, PulseNode):
			return self.render_component(node, path)
		if isinstance(node, Element):
			return self.render_node(node, path)
		if isinstance(node, Value):
			json_value = coerce_json(cast(JsonCoercible, node.value), path)
			return json_value, json_value
		if isinstance(node, Expr):
			return node.render(), node
		if is_json_primitive(node):
			return node, node
		raise TypeError(f"Unsupported node type: {type(node).__name__}")

	def render_component(
		self, component: PulseNode, path: RenderPath
	) -> tuple[VDOM, PulseNode]:
		if component.hooks is None:
			component.hooks = HookContext()
		with component.hooks:
			rendered = component.fn(*component.args, **component.kwargs)
		vdom, normalized_child = self.render_tree(rendered, path)
		component.contents = normalized_child
		return vdom, component

	def render_node(
		self, element: Element, path: RenderPath
	) -> tuple[VDOMNode, Element]:
		tag = self.render_tag(element.tag)
		vdom_node: VDOMElement = {"tag": tag}
		if (key_val := key_value(element)) is not None:
			vdom_node["key"] = key_val

		props = element.props or {}
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
		normalized_children: list[NormalizedNode] = []
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
		previous: NormalizedNode,
		current: RenderInput,
		path: RenderPath = "",
	) -> NormalizedNode:
		if isinstance(current, Value):
			current = coerce_json(current.value, path)
		if isinstance(previous, Value):
			previous = coerce_json(previous.value, path)
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
		path: RenderPath,
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
		path: RenderPath,
	) -> Element:
		prev_props = previous.props or {}
		new_props = current.props or {}
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
		c1: list[NormalizedNode],
		c2: list[RenderInput],
		path: RenderPath,
	) -> list[NormalizedNode]:
		if not c1 and not c2:
			return []

		N1 = len(c1)
		N2 = len(c2)
		norm: list[NormalizedNode | None] = [None] * N2
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
		previous: dict[str, NormalizedPropValue],
		current: dict[str, PropInput],
		path: RenderPath,
		prev_eval: set[str],
	) -> DiffPropsResult:
		updated: dict[str, VDOMPropValue] = {}
		normalized: dict[str, NormalizedPropValue] | None = None
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
						normalized = cast(
							dict[str, NormalizedPropValue], current.copy()
						)
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
						normalized = cast(
							dict[str, NormalizedPropValue], current.copy()
						)
					normalized[key] = normalized_value
					updated[key] = cast(VDOMPropValue, vdom_value)
				continue

			if isinstance(value, Value):
				json_value = coerce_json(cast(JsonCoercible, value.value), prop_path)
				if normalized is None:
					normalized = cast(dict[str, NormalizedPropValue], current.copy())
				normalized[key] = json_value
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if key not in previous or not values_equal(json_value, old_value):
					updated[key] = cast(VDOMPropValue, json_value)
				continue

			if isinstance(value, Expr):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = cast(dict[str, NormalizedPropValue], current.copy())
				normalized[key] = value
				if not (isinstance(old_value, Expr) and values_equal(old_value, value)):
					updated[key] = value.render()
				continue

			if callable(value):
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = cast(dict[str, NormalizedPropValue], current.copy())
				normalized[key] = value
				register_callback(self.callbacks, prop_path, value)
				if not callable(old_value):
					updated[key] = CALLBACK_PLACEHOLDER
				continue

			json_value = coerce_json(value, prop_path)
			if isinstance(old_value, (Element, PulseNode)):
				unmount_element(old_value)
			if normalized is not None:
				normalized[key] = json_value
			elif json_value is not value:
				normalized = cast(dict[str, NormalizedPropValue], current.copy())
				normalized[key] = json_value
			if key not in previous or not values_equal(json_value, old_value):
				updated[key] = cast(VDOMPropValue, json_value)

		for key in removed_keys:
			old_value = previous.get(key)
			if isinstance(old_value, (Element, PulseNode)):
				unmount_element(old_value)

		normalized_props = (
			normalized
			if normalized is not None
			else cast(dict[str, NormalizedPropValue], current.copy())
		)
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

	def render_tag(self, tag: str | Expr) -> str:
		if isinstance(tag, str):
			if tag == "":
				return FRAGMENT_TAG
			if tag.startswith(MOUNT_PREFIX):
				return tag
			return tag

		key = self.register_component_expr(tag)
		return f"{MOUNT_PREFIX}{key}"

	def register_component_expr(self, expr: Expr) -> str:
		ref = registry_ref(expr)
		if ref is None:
			raise TypeError(
				"Component tag expressions must be registry-backed Expr values "
				+ "(Import/JsFunction/Constant/JsxFunction)."
			)
		return ref["key"]

	# ------------------------------------------------------------------
	# Unmount helper
	# ------------------------------------------------------------------

	def unmount_subtree(self, node: NormalizedNode) -> None:
		unmount_element(node)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def registry_ref(expr: Expr) -> RegistryRef | None:
	if isinstance(expr, (Import, JsFunction, Constant, JsxFunction)):
		return {"t": "ref", "key": expr.id}
	return None


def is_json_primitive(value: RenderInput | JsonCoercible | Primitive) -> bool:
	return value is None or isinstance(value, (str, int, float, bool))


def coerce_json(value: JsonCoercible, path: str) -> JsonValue:
	if is_json_primitive(value):
		return cast(JsonPrimitive, value)
	if isinstance(value, (list, tuple)):
		return [coerce_json(v, path) for v in value]
	if isinstance(value, dict):
		out: dict[str, JsonValue] = {}
		for k, v in value.items():
			if not isinstance(k, str):
				raise TypeError(f"Non-string prop key at {path}: {k!r}")
			out[k] = coerce_json(v, path)
		return out
	raise TypeError(f"Unsupported JSON value at {path}: {type(value).__name__}")


def prop_requires_eval(value: NormalizedPropValue) -> bool:
	if isinstance(value, Value):
		return False
	if isinstance(value, (Element, PulseNode)):
		return True
	if isinstance(value, Expr):
		return True
	return callable(value)


def eval_keys_for_props(props: dict[str, NormalizedPropValue]) -> set[str]:
	eval_keys: set[str] = set()
	for key, value in props.items():
		if prop_requires_eval(value):
			eval_keys.add(key)
	return eval_keys


def normalize_children(children: Sequence[ChildInput] | None) -> list[NormalizedNode]:
	if not children:
		return []

	out: list[NormalizedNode] = []
	seen_keys: set[str] = set()

	def register_key(item: NormalizedNode) -> None:
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

	def visit(item: ChildInput) -> None:
		if isinstance(item, dict):
			raise TypeError("Dict is not a valid child; wrap in Value for props")
		if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
			for sub in item:
				visit(sub)
		else:
			register_key(item)
			out.append(item)

	for child in children:
		visit(child)

	return out


def register_callback(
	callbacks: Callbacks,
	path: RenderPath,
	fn: CallbackFn,
) -> None:
	n_args = len(inspect.signature(fn).parameters)
	callbacks[path] = Callback(fn=fn, n_args=n_args)


def join_path(prefix: RenderPath, path: str | int) -> RenderPath:
	if prefix:
		return f"{prefix}.{path}"
	return str(path)


def same_node(left: NormalizedNode, right: RenderInput) -> bool:
	if values_equal(left, right):
		return True
	if isinstance(left, Element) and isinstance(right, Element):
		return values_equal(left.tag, right.tag) and key_value(left) == key_value(right)
	if isinstance(left, PulseNode) and isinstance(right, PulseNode):
		return left.fn == right.fn and key_value(left) == key_value(right)
	return False


def key_value(node: NormalizedNode | RenderInput) -> str | None:
	key = getattr(node, "key", None)
	if isinstance(key, Literal):
		if not isinstance(key.value, str):
			raise TypeError("Element key must be a string")
		return key.value
	return cast(str | None, key)


def unmount_element(element: NormalizedNode) -> None:
	if isinstance(element, PulseNode):
		if element.contents is not None:
			unmount_element(element.contents)
			element.contents = None
		if element.hooks is not None:
			element.hooks.unmount()
		return

	if isinstance(element, Element):
		props = element.props or {}
		for value in props.values():
			if isinstance(value, (Element, PulseNode)):
				unmount_element(value)
		for child in normalize_children(element.children):
			unmount_element(child)
		element.children = []
		return
