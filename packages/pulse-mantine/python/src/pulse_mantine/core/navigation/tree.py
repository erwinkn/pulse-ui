from typing import Any, Optional, Unpack
import pulse as ps


ExpandedState = dict[str, bool]


class MantineTreeProps(ps.HTMLDivProps, total=False):
    data: list[dict[str, Any]]
    levelOffset: int
    selectOnClick: bool
    clearSelectionOnOutsideClick: bool
    className: str
    classNames: dict[str, str]
    styles: dict[str, Any]
    style: dict[str, Any]


@ps.react_component("Tree", "pulse-mantine")
def TreeInternal(
    *children: ps.Child,
    key: Optional[str] = None,
    channelId: Optional[str] = None,
    initialExpandedState: Optional[ExpandedState] = None,
    autoSync: bool = True,
    # useTree options (forwarded to the JS wrapper)
    initialSelectedState: Optional[list[str]] = None,
    initialCheckedState: Optional[list[str]] = None,
    multiple: Optional[bool] = None,
    **props: Unpack[MantineTreeProps],
): ...


class TreeState(ps.State):
    def __init__(
        self,
        *,
        autoSync: bool = True,
        initialExpandedState: Optional[ExpandedState] = None,
        # useTree options
        initialSelectedState: Optional[list[str]] = None,
        initialCheckedState: Optional[list[str]] = None,
        multiple: Optional[bool] = None,
    ):
        self._channel = ps.channel()
        self._expanded: ExpandedState = dict(initialExpandedState or {})
        self._auto_sync = bool(autoSync)
        self._initial_selected = list(initialSelectedState or [])
        self._initial_checked = list(initialCheckedState or [])
        self._multiple = multiple
        # Client -> server per-node events
        self._channel.on("nodeExpand", self._on_node_expand)
        self._channel.on("nodeCollapse", self._on_node_collapse)

    # Public imperative API mirrors Mantine useTree
    def toggle_expanded(self, value: str):
        if not isinstance(value, str):
            return
        self._channel.emit("toggleExpanded", {"value": value})

    def expand(self, value: str):
        if not isinstance(value, str):
            return
        self._channel.emit("expand", {"value": value})

    def collapse(self, value: str):
        if not isinstance(value, str):
            return
        self._channel.emit("collapse", {"value": value})

    def expand_all_nodes(self):
        self._channel.emit("expandAllNodes")

    def collapse_all_nodes(self):
        self._channel.emit("collapseAllNodes")

    def set_expanded_state(self, state: ExpandedState):
        if not isinstance(state, dict):
            return
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

    async def get_checked_nodes(self) -> list[dict[str, Any]]:
        result = await self._channel.request("getCheckedNodes")
        return result or []

    @property
    def expanded_state(self) -> ExpandedState:
        return self._expanded

    # Client sync handlers
    def _on_node_expand(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        value = payload.get("value")
        if isinstance(value, str) and value:
            self._expanded[value] = True

    def _on_node_collapse(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        value = payload.get("value")
        if isinstance(value, str) and value:
            self._expanded[value] = False

    # Render the React wrapper component
    def render(
        self,
        *children: ps.Child,
        key: Optional[str] = None,
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
    key: Optional[str] = None,
    state: Optional[TreeState] = None,
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
