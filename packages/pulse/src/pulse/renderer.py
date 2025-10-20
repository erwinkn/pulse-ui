import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
	Any,
	Literal,
	NamedTuple,
	TypeAlias,
	TypedDict,
	cast,
)

from pulse.css import CssReference
from pulse.helpers import values_equal
from pulse.vdom import (
	VDOM,
	Callback,
	Callbacks,
	ComponentNode,
	Element,
	Node,
	Props,
	VDOMNode,
)


class ReplaceOperation(TypedDict):
	type: Literal["replace"]
	path: str
	data: VDOM


# This payload makes it easy for the client to rebuild an array of React nodes
# from the previous children array:
# - Allocate array of size N
# - For i in 0..N-1, check the following scenarios
#   - i matches the next index in `new` -> use provided tree
#   - i matches the next index in `reuse` -> reuse previous child
#   - otherwise, reuse the element at the same index
class ReconciliationOperation(TypedDict):
	type: Literal["reconciliation"]
	path: str
	N: int
	new: tuple[list[int], list[VDOM]]
	reuse: tuple[list[int], list[int]]


class UpdatePropsDelta(TypedDict, total=False):
	# Only send changed/new keys under `set` and removed keys under `remove`
	set: Props
	remove: list[str]


class UpdatePropsOperation(TypedDict):
	type: Literal["update_props"]
	path: str
	data: UpdatePropsDelta


class PathDelta(TypedDict, total=False):
	add: list[str]
	remove: list[str]


class UpdateCallbacksOperation(TypedDict):
	type: Literal["update_callbacks"]
	path: str
	data: PathDelta


class UpdateCssRefsOperation(TypedDict):
	type: Literal["update_css_refs"]
	path: str
	data: PathDelta


class UpdateRenderPropsOperation(TypedDict):
	type: Literal["update_render_props"]
	path: str
	data: PathDelta


VDOMOperation: TypeAlias = (
	# InsertOperation,
	# RemoveOperation,
	ReplaceOperation
	| UpdatePropsOperation
	# | MoveOperation,
	| ReconciliationOperation
	| UpdateCallbacksOperation
	| UpdateCssRefsOperation
	| UpdateRenderPropsOperation
)

RenderPath: TypeAlias = str


class RenderTree:
	root: Element
	callbacks: Callbacks
	render_props: set[str]
	css_refs: set[str]

	def __init__(self, root: Element) -> None:
		self.root = root
		self.callbacks = {}
		self.render_props = set()
		self.css_refs = set()
		self._normalized: Element | None = None

	def render(self) -> VDOM:
		renderer = Renderer()
		vdom, normalized = renderer.render_tree(self.root)
		self.root = normalized
		self.callbacks = renderer.callbacks
		self.render_props = renderer.render_props
		self.css_refs = renderer.css_refs
		self._normalized = normalized
		return vdom

	def diff(self, new_tree: Element) -> list[VDOMOperation]:
		if self._normalized is None:
			raise RuntimeError("RenderTree.render must be called before diff")

		renderer = Renderer()
		normalized = renderer.reconcile_tree(self._normalized, new_tree, path="")

		callback_prev = set(self.callbacks.keys())
		callback_next = set(renderer.callbacks.keys())
		callback_add = sorted(callback_next - callback_prev)
		callback_remove = sorted(callback_prev - callback_next)

		render_props_prev = self.render_props
		render_props_next = renderer.render_props
		render_props_add = sorted(render_props_next - render_props_prev)
		render_props_remove = sorted(render_props_prev - render_props_next)

		css_prev = self.css_refs
		css_next = renderer.css_refs
		css_add = sorted(css_next - css_prev)
		css_remove = sorted(css_prev - css_next)

		prefix: list[VDOMOperation] = []

		if css_add or css_remove:
			css_delta: PathDelta = {}
			if css_add:
				css_delta["add"] = css_add
			if css_remove:
				css_delta["remove"] = css_remove
			prefix.append(
				UpdateCssRefsOperation(type="update_css_refs", path="", data=css_delta)
			)

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

		ops = prefix + renderer.operations if prefix else renderer.operations

		self.callbacks = renderer.callbacks
		self.render_props = renderer.render_props
		self.css_refs = renderer.css_refs
		self._normalized = normalized
		self.root = normalized

		return ops

	def unmount(self) -> None:
		if self._normalized is not None:
			unmount_element(self._normalized)
			self._normalized = None
		self.callbacks.clear()
		self.render_props.clear()
		self.css_refs.clear()


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
		self.css_refs: set[str] = set()
		self.operations: list[VDOMOperation] = []

	# ------------------------------------------------------------------
	# Rendering helpers
	# ------------------------------------------------------------------

	def render_tree(self, node: Element, path: RenderPath = "") -> tuple[VDOM, Element]:
		if isinstance(node, ComponentNode):
			return self.render_component(node, path)
		if isinstance(node, Node):
			return self.render_node(node, path)
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

			if isinstance(value, CssReference):
				if isinstance(old_value, (Node, ComponentNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				self.css_refs.add(prop_path)
				if not isinstance(old_value, CssReference) or old_value != value:
					updated[key] = _css_ref_token(value)
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


def extract_key(element: Element) -> str | None:
	if isinstance(element, ComponentNode):
		return element.key
	if isinstance(element, Node):
		return element.key
	return None


def child_key(element: Element, index: int) -> str:
	key = extract_key(element)
	if key is not None:
		return key
	return f"__idx__{index}"


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


def lis(seq: list[int]) -> list[int]:
	if not seq:
		return []
	tails: list[int] = []
	prev: list[int] = [-1] * len(seq)
	for i, v in enumerate(seq):
		lo, hi = 0, len(tails)
		while lo < hi:
			mid = (lo + hi) // 2
			if seq[tails[mid]] < v:
				lo = mid + 1
			else:
				hi = mid
		if lo > 0:
			prev[i] = tails[lo - 1]
		if lo == len(tails):
			tails.append(i)
		else:
			tails[lo] = i
	lis_indices: list[int] = []
	k = tails[-1] if tails else -1
	while k != -1:
		lis_indices.append(k)
		k = prev[k]
	lis_indices.reverse()
	return lis_indices


def _css_ref_token(ref: CssReference) -> str:
	return f"{ref.module.id}:{ref.name}"


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
