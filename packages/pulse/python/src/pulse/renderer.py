from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from types import NoneType
from typing import Any, NamedTuple, TypeAlias, cast
from typing import Literal as TypingLiteral

from pulse.context import PulseContext
from pulse.debounce import Debounced
from pulse.helpers import values_equal
from pulse.hooks.core import HookContext
from pulse.reactive import RenderEffect, Scope, Untrack
from pulse.refs import RefHandle
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

PropValue: TypeAlias = Node | Callable[..., Any] | Debounced[Any, Any] | RefHandle[Any]

FRAGMENT_TAG = ""
MOUNT_PREFIX = "$$"
CALLBACK_PLACEHOLDER = "$cb"

logger = logging.getLogger(__name__)


def enforce_scope_ownership(scope: Scope, component: PulseNode) -> None:
	"""Flag Effects/States constructed during a render pass without an owner.

	Everything with a designated owner is shielded from (or removed from) the
	component's tracking scope: inline @ps.effect (inline-effects hook),
	ps.init/ps.setup creations (their own capture scopes), ps.state factories,
	hook-state factories, and shared/global states (Untrack). Whatever is left
	would never be disposed, so it leaks past unmount. Policy comes from
	App(unowned_reactives=...): "error" (default), "warn", or "ignore".
	"""
	if not scope.effects and not scope.states:
		return
	policy = PulseContext.get().app.unowned_reactives
	if policy == "ignore":
		return
	component_name = component.name or getattr(component.fn, "__name__", "component")
	created = [f"Effect '{effect.name or 'unnamed'}'" for effect in scope.effects]
	created += [type(state).__name__ for state in scope.states]
	message = (
		f"Component '{component_name}' created reactive objects during render "
		f"with no owner to dispose them: {', '.join(created)}. Create states in "
		"`with ps.init():` or via `ps.state(...)`, and effects with `@ps.effect` "
		"or inside a State. Configure this check with App(unowned_reactives=...)."
	)
	if policy == "warn":
		logger.warning(message)
		return
	for effect in scope.effects:
		if not effect.__disposed__:
			effect.dispose()
	for state in scope.states:
		if not state.__disposed__:
			state.dispose()
	raise RuntimeError(message)


class Callback(NamedTuple):
	fn: Callable[..., Any]
	n_args: int
	accepts_varargs: bool = False


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


class ComponentRuntime:
	"""Persistent render state for one component instance.

	Lives on the first PulseNode instance rendered for the component and moves
	to each new instance during reconciliation. The render effect re-renders
	only this component's subtree when its dependencies change.
	"""

	__slots__ = ("node", "path", "tree", "effect")  # pyright: ignore[reportUnannotatedClassAttribute]

	node: PulseNode
	path: str
	tree: "RenderTree"
	effect: RenderEffect | None

	def __init__(self, node: PulseNode, path: str, tree: "RenderTree") -> None:
		self.node = node
		self.path = path
		self.tree = tree
		self.effect = None


class RenderTree:
	"""Persistent render state for a view.

	Holds the normalized node tree and the callback registry, and dispatches
	fine-grained component re-renders. The owning View installs `dispatch` to
	wrap passes with Pulse context and ship the resulting operations to the
	client; without a dispatcher (tests, standalone trees), operations
	accumulate in `pending_ops`.
	"""

	element: Node
	callbacks: Callbacks
	rendered: bool
	dispatch: Callable[[ComponentRuntime], None] | None
	pending_ops: list[VDOMOperation]

	def __init__(self, element: Node) -> None:
		self.element = element
		self.callbacks = {}
		self.rendered = False
		self.dispatch = None
		self.pending_ops = []

	def render(self) -> VDOM:
		"""First render (or full re-render for a fresh prerender). Returns VDOM."""
		renderer = Renderer(tree=self)
		vdom, self.element = renderer.render_tree(self.element)
		renderer.finish_pass()
		self.rendered = True
		return vdom

	def rerender(self, new_element: Node | None = None) -> list[VDOMOperation]:
		"""Reconcile the whole tree from the root and return update operations.

		If new_element is provided, reconciles against it (for testing).
		Otherwise, reconciles against the current element.
		"""
		if not self.rendered:
			raise RuntimeError("render() must be called before rerender()")
		target = new_element if new_element is not None else self.element
		renderer = Renderer(tree=self)
		self.element = renderer.reconcile_tree(self.element, target, path="")
		renderer.finish_pass()
		return renderer.operations

	def run_component_pass(self, runtime: ComponentRuntime) -> list[VDOMOperation]:
		"""Re-render a single component subtree, returning its operations."""
		renderer = Renderer(tree=self, pass_root=runtime.path)
		renderer.rerender_component(runtime)
		renderer.finish_pass()
		return renderer.operations

	def _dispatch(self, runtime: ComponentRuntime) -> None:
		if self.dispatch is not None:
			self.dispatch(runtime)
			return
		self.pending_ops.extend(self.run_component_pass(runtime))

	def take_ops(self) -> list[VDOMOperation]:
		"""Drain operations accumulated without a dispatcher."""
		ops = self.pending_ops
		self.pending_ops = []
		return ops

	def iter_runtimes(self) -> "Iterator[ComponentRuntime]":
		yield from iter_component_runtimes(self.element)

	def pause_effects(self) -> None:
		for runtime in self.iter_runtimes():
			if runtime.effect is not None:
				runtime.effect.pause()

	def resume_effects(self) -> None:
		for runtime in self.iter_runtimes():
			if runtime.effect is not None:
				runtime.effect.resume()

	def flush_effects(self) -> None:
		for runtime in self.iter_runtimes():
			if runtime.effect is not None:
				runtime.effect.flush()

	def unmount(self) -> None:
		if self.rendered:
			unmount_element(self.element)
			self.rendered = False
		self.callbacks.clear()
		self.pending_ops = []


class Renderer:
	"""Single render/reconcile pass over (part of) a tree.

	Persistent mode requires a RenderTree: callbacks are registered into the
	tree's persistent registry, and callbacks under `pass_root` that are not
	re-registered during the pass are swept when it finishes. Snapshot mode
	renders one-shot VDOM with callbacks/refs stripped.
	"""

	def __init__(
		self,
		*,
		tree: RenderTree | None = None,
		pass_root: str = "",
		mode: TypingLiteral["persistent", "snapshot"] = "persistent",
	) -> None:
		self.mode: TypingLiteral["persistent", "snapshot"] = mode
		self.tree: RenderTree | None = tree
		self.pass_root: str = pass_root
		self.callbacks: Callbacks = tree.callbacks if tree is not None else {}
		self.operations: list[VDOMOperation] = []
		self._stale_callbacks: set[str] = set()
		if tree is not None:
			if pass_root:
				prefix = pass_root + "."
				self._stale_callbacks = {
					key
					for key in self.callbacks
					if key == pass_root or key.startswith(prefix)
				}
			else:
				self._stale_callbacks = set(self.callbacks)

	def register_callback(self, path: str, fn: Callable[..., Any]) -> None:
		register_callback(self.callbacks, path, fn)
		self._stale_callbacks.discard(path)

	def finish_pass(self) -> None:
		"""Drop callbacks under the pass root that were not re-registered."""
		for key in self._stale_callbacks:
			self.callbacks.pop(key, None)
		self._stale_callbacks = set()

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
		if self.mode == "snapshot":
			if component.hooks is None:
				component.hooks = HookContext()
			with component.hooks:
				rendered = component.fn(*component.args, **component.kwargs)
			vdom, normalized_child = self.render_tree(rendered, path)
			component.contents = normalized_child
			return vdom, component

		tree = self.tree
		if tree is None:
			raise RuntimeError(
				"Rendering components persistently requires a RenderTree"
			)
		runtime = component.runtime
		if runtime is None:
			runtime = ComponentRuntime(component, path, tree)
			component.runtime = runtime
		else:
			# Full re-render of an already-rendered component (fresh prerender):
			# tear down the old subtree so stale effects don't stay subscribed.
			runtime.node = component
			runtime.path = path
			if component.contents is not None:
				unmount_element(component.contents)
				component.contents = None
		if runtime.effect is None:
			# Untrack: the runtime owns its render effect; it must not register
			# into the enclosing (parent) component's tracking scope.
			with Untrack():
				runtime.effect = RenderEffect(
					_make_component_effect(tree, runtime),
					lazy=True,
					name=f"render:{component.name or getattr(component.fn, '__name__', 'component')}",
				)
			runtime.effect.runtime = runtime
		if component.hooks is None:
			component.hooks = HookContext()
		# Untrack shields the enclosing component's scope: this component's
		# reads (and its effect) must not become dependencies of its parent.
		with Untrack():
			with runtime.effect.capture_deps(update_deps=True) as scope:
				with component.hooks:
					rendered = component.fn(*component.args, **component.kwargs)
				vdom, normalized_child = self.render_tree(rendered, path)
			enforce_scope_ownership(scope, component)
		runtime.effect.runs += 1
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

		if self.mode == "snapshot":
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

		tree = self.tree
		if tree is None:
			raise RuntimeError(
				"Rendering components persistently requires a RenderTree"
			)
		runtime = previous.runtime
		if runtime is None:
			runtime = ComponentRuntime(current, path, tree)
		current.runtime = runtime
		if previous is not current:
			previous.runtime = None
		runtime.node = current
		runtime.path = path
		if runtime.effect is None:
			# Untrack: the runtime owns its render effect; it must not register
			# into the enclosing (parent) component's tracking scope.
			with Untrack():
				runtime.effect = RenderEffect(
					_make_component_effect(tree, runtime),
					lazy=True,
					name=f"render:{current.name or getattr(current.fn, '__name__', 'component')}",
				)
			runtime.effect.runtime = runtime
		else:
			# This pass re-renders the component now; a queued standalone run
			# would be redundant.
			runtime.effect.cancel(cancel_interval=False)

		with Untrack():
			with runtime.effect.capture_deps(update_deps=True) as scope:
				with current.hooks:
					rendered = current.fn(*current.args, **current.kwargs)

				if current.contents is None:
					new_vdom, normalized = self.render_tree(rendered, path)
					current.contents = normalized
					self.operations.append(
						ReplaceOperation(type="replace", path=path, data=new_vdom)
					)
				else:
					current.contents = self.reconcile_tree(
						current.contents, rendered, path
					)
			enforce_scope_ownership(scope, current)
		runtime.effect.runs += 1

		return current

	def rerender_component(self, runtime: ComponentRuntime) -> None:
		"""Standalone re-render of one component, triggered by its effect."""
		component = runtime.node
		path = runtime.path
		assert runtime.effect is not None
		if component.hooks is None:
			component.hooks = HookContext()
		with Untrack():
			with runtime.effect.capture_deps(update_deps=True) as scope:
				with component.hooks:
					rendered = component.fn(*component.args, **component.kwargs)
				if component.contents is None:
					new_vdom, normalized = self.render_tree(rendered, path)
					component.contents = normalized
					self.operations.append(
						ReplaceOperation(type="replace", path=path, data=new_vdom)
					)
				else:
					component.contents = self.reconcile_tree(
						component.contents, rendered, path
					)
			enforce_scope_ownership(scope, component)
		runtime.effect.runs += 1

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

			if value is None:
				if normalized is None:
					normalized = current.copy()
				normalized.pop(key, None)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if key in previous and old_value is not None:
					removed_keys.add(key)
				continue

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

			if isinstance(value, RefHandle):
				if self.mode == "snapshot":
					if normalized is None:
						normalized = current.copy()
					normalized.pop(key, None)
					continue
				if key != "ref":
					raise TypeError("RefHandle can only be used as the 'ref' prop")
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				if not (
					isinstance(old_value, RefHandle) and values_equal(old_value, value)
				):
					updated[key] = {
						"__pulse_ref__": {
							"channelId": value.channel_id,
							"refId": value.id,
						}
					}
				continue
			if isinstance(value, Debounced):
				if self.mode == "snapshot":
					if normalized is None:
						normalized = current.copy()
					normalized.pop(key, None)
					continue
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				self.register_callback(prop_path, value.fn)
				prev_delay = (
					old_value.delay_ms if isinstance(old_value, Debounced) else None
				)
				if prev_delay != value.delay_ms:
					updated[key] = format_callback_placeholder(value.delay_ms)
				continue

			if callable(value):
				if self.mode == "snapshot":
					if normalized is None:
						normalized = current.copy()
					normalized.pop(key, None)
					continue
				eval_keys.add(key)
				if isinstance(old_value, (Element, PulseNode)):
					unmount_element(old_value)
				if normalized is None:
					normalized = current.copy()
				normalized[key] = value
				self.register_callback(prop_path, value)
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


def _make_component_effect(tree: RenderTree, runtime: ComponentRuntime):
	def run() -> None:
		tree._dispatch(runtime)  # pyright: ignore[reportPrivateUsage]

	return run


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
	if isinstance(value, RefHandle):
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
	params = inspect.signature(fn).parameters.values()
	accepts_varargs = any(p.kind is p.VAR_POSITIONAL for p in params)
	n_args = sum(
		1
		for p in params
		if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
		and p.default is p.empty
	)
	callbacks[path] = Callback(fn=fn, n_args=n_args, accepts_varargs=accepts_varargs)


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


def iter_component_runtimes(node: Node) -> "Iterator[ComponentRuntime]":
	"""Yield every ComponentRuntime in a normalized subtree."""
	if isinstance(node, PulseNode):
		if node.runtime is not None:
			yield node.runtime
		if node.contents is not None:
			yield from iter_component_runtimes(node.contents)
		return
	if isinstance(node, Element):
		if isinstance(node.props, dict):
			for value in node.props.values():
				if isinstance(value, (Element, PulseNode)):
					yield from iter_component_runtimes(value)
		for child in normalize_children(node.children):
			yield from iter_component_runtimes(child)


def unmount_element(element: Node) -> None:
	if isinstance(element, PulseNode):
		runtime = element.runtime
		if runtime is not None:
			if runtime.effect is not None:
				runtime.effect.dispose()
				runtime.effect = None
			element.runtime = None
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
