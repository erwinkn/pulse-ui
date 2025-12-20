from typing import Literal, TypedDict, Unpack

from pulse.dom.props import HTMLAnchorProps
from pulse.transpiler_v2.react_component import react_component
from pulse.vdom import Child


class LinkPath(TypedDict):
	pathname: str
	search: str
	hash: str


# @react_component("Link", "react-router", version="^7")
@react_component("Link", "react-router")
def Link(
	*children: Child,
	key: str | None = None,
	to: str,
	discover: Literal["render", "none"] | None = None,
	prefetch: Literal["none", "intent", "render", "viewport"] = "intent",
	preventScrollReset: bool | None = None,
	relative: Literal["route", "path"] | None = None,
	reloadDocument: bool | None = None,
	replace: bool | None = None,
	state: dict[str, object] | None = None,
	viewTransition: bool | None = None,
	**props: Unpack[HTMLAnchorProps],
): ...


# @react_component("Outlet", "react-router", version="^7")
@react_component("Outlet", "react-router")
def Outlet(key: str | None = None): ...


__all__ = ["Link", "Outlet"]
