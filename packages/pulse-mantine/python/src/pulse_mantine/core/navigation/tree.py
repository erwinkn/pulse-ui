from typing import Any, Unpack

import pulse as ps
from pulse.helpers import call_flexible, create_task, maybe_await

ExpandedState = dict[str, bool]


class MantineTreeProps(ps.HTMLDivProps, total=False):
	data: list[dict[str, Any]]
	levelOffset: int
	selectOnClick: bool
	clearSelectionOnOutsideClick: bool
	className: str | ps.CssReference
	classNames: dict[str, str]
	styles: dict[str, Any]
	style: dict[str, Any]


@ps.react_component("Tree", "pulse-mantine")
def TreeInternal(
	*children: ps.Child,
	key: str | None = None,
	channelId: str | None = None,
	initialExpandedState: ExpandedState | None = None,
	autoSync: bool = True,
	# useTree options (forwarded to the JS wrapper)
	initialSelectedState: list[str] | None = None,
	initialCheckedState: list[str] | None = None,
	multiple: bool | None = None,
	**props: Unpack[MantineTreeProps],
): ...


class TreeState(ps.State):
	def __init__(
		self,
		*,
		autoSync: bool = True,
		initialExpandedState: ExpandedState | None = None,
		# useTree options
		initialSelectedState: list[str] | None = None,
		initialCheckedState: list[str] | None = None,
		multiple: bool | None = None,
		onNodeExpand: ps.EventHandler1[str] | None = None,
		onNodeCollapse: ps.EventHandler1[str] | None = None,
	):
		self._channel = ps.channel()
		self._expanded: ExpandedState = dict(initialExpandedState or {})
		self._auto_sync = bool(autoSync)
		self._initial_selected = list(initialSelectedState or [])
		self._initial_checked = list(initialCheckedState or [])
		self._multiple = multiple
		self._on_node_expand_listener = onNodeExpand
		self._on_node_collapse_listener = onNodeCollapse
		# Client -> server per-node events
		self._channel.on("nodeExpand", self._on_node_expand)
		self._channel.on("nodeCollapse", self._on_node_collapse)

	# Public imperative API mirrors Mantine useTree
	def toggle_expanded(self, value: str):
		self._channel.emit("toggleExpanded", {"value": value})

	def expand(self, value: str):
		self._channel.emit("expand", {"value": value})

	def collapse(self, value: str):
		self._channel.emit("collapse", {"value": value})

	def expand_all_nodes(self):
		self._channel.emit("expandAllNodes")

	def collapse_all_nodes(self):
		self._channel.emit("collapseAllNodes")

	def set_expanded_state(self, state: ExpandedState):
		self._expanded.clear()
		self._expanded.update({k: bool(v) for k, v in state.items()})
		self._channel.emit("setExpandedState", {"expandedState": dict(self._expanded)})

	async def get_expanded_state(self) -> ExpandedState:
		result = await self._channel.request("getExpandedState")
		if isinstance(result, dict):
			# Update local cache with the result
			self._expanded.clear()
			self._expanded.update({k: bool(v) for k, v in result.items()})
		return dict(self._expanded)

	# Selection API
	def toggle_selected(self, value: str):
		self._channel.emit("toggleSelected", {"value": value})

	def select(self, value: str):
		self._channel.emit("select", {"value": value})

	def deselect(self, value: str):
		self._channel.emit("deselect", {"value": value})

	def clear_selected(self):
		self._channel.emit("clearSelected")

	def set_selected_state(self, values: list[str]):
		self._channel.emit("setSelectedState", {"selectedState": list(values or [])})

	async def get_selected_state(self) -> list[str]:
		result = await self._channel.request("getSelectedState")
		return list(result or []) if isinstance(result, list) else []

	async def get_anchor_node(self) -> str | None:
		result = await self._channel.request("getAnchorNode")
		return str(result) if isinstance(result, str) else None

	# Hover API
	def set_hovered_node(self, value: str | None):
		self._channel.emit("setHoveredNode", {"value": value})

	async def get_hovered_node(self) -> str | None:
		result = await self._channel.request("getHoveredNode")
		return str(result) if isinstance(result, str) else None

	# Checked API
	def check_node(self, value: str):
		self._channel.emit("checkNode", {"value": value})

	def uncheck_node(self, value: str):
		self._channel.emit("uncheckNode", {"value": value})

	def check_all_nodes(self):
		self._channel.emit("checkAllNodes")

	def uncheck_all_nodes(self):
		self._channel.emit("uncheckAllNodes")

	def set_checked_state(self, values: list[str]):
		self._channel.emit("setCheckedState", {"checkedState": list(values or [])})

	async def get_checked_nodes(self) -> list[dict[str, Any]]:
		result = await self._channel.request("getCheckedNodes")
		return result or []

	async def get_checked_state(self) -> list[str]:
		result = await self._channel.request("getCheckedState")
		return list(result or []) if isinstance(result, list) else []

	async def is_node_checked(self, value: str) -> bool:
		result = await self._channel.request("isNodeChecked", {"value": value})
		return bool(result)

	async def is_node_indeterminate(self, value: str) -> bool:
		result = await self._channel.request("isNodeIndeterminate", {"value": value})
		return bool(result)

	@property
	def expanded_state(self) -> ExpandedState:
		return self._expanded

	# Client sync handlers
	async def _on_node_expand(self, payload: dict[str, Any]) -> None:
		if not isinstance(payload, dict):
			return
		value = payload.get("value")
		if isinstance(value, str) and value:
			self._expanded[value] = True
			listener = self._on_node_expand_listener
			if listener is not None:
				create_task(maybe_await(call_flexible(listener, value)))

	def _on_node_collapse(self, payload: dict[str, Any]) -> None:
		if not isinstance(payload, dict):
			return
		value = payload.get("value")
		if isinstance(value, str) and value:
			self._expanded[value] = False
			listener = self._on_node_collapse_listener
			if listener is not None:
				create_task(maybe_await(call_flexible(listener, value)))

	# Render the React wrapper component
	def render(
		self,
		*children: ps.Child,
		key: str | None = None,
		**props: Unpack[MantineTreeProps],
	):
		return TreeInternal(
			*children,
			key=key,
			channelId=self._channel.id,
			initialExpandedState=dict(self._expanded),
			autoSync=self._auto_sync,
			initialSelectedState=self._initial_selected,
			initialCheckedState=self._initial_checked,
			multiple=self._multiple,
			**props,
		)


def Tree(
	*children: ps.Child,
	key: str | None = None,
	state: TreeState | None = None,
	**props: Unpack[MantineTreeProps],
):
	if state is None:
		# No server state: render uncontrolled client Tree with no channel
		return TreeInternal(
			*children,
			key=key,
			channelId=None,
			# Let client use its own defaults for useTree; user can pass
			# Mantine props via **props.
			**props,
		)
	# With server state: delegate to state's render to include channel + options
	return state.render(*children, key=key, **props)
