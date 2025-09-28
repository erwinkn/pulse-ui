from typing import Literal, Optional, TypedDict, Unpack
from pulse.html.props import HTMLAnchorProps
from pulse.vdom import Child
from ..react_component import DEFAULT, react_component


class LinkPath(TypedDict):
    pathname: str
    search: str
    hash: str


@react_component("Link", "react-router")
def Link(
    *children: Child,
    key: Optional[str] = None,
    to: str,
    # Default: render
    discover: Literal["render", "none"] = DEFAULT,
    # The React Router default is 'none' to match the behavior of regular links,
    # but 'intent' is more desirable in general
    prefetch: Literal["none", "intent", "render", "viewport"] = "intent",
    # Default: False
    preventScrollReset: bool = DEFAULT,
    # Default: 'route'
    relative: Literal["route", "path"] = DEFAULT,
    # Default: False
    reloadDocument: bool = DEFAULT,
    # Default: False
    replace: bool = DEFAULT,
    # Default: undefined
    state: dict = DEFAULT,
    # Default: False
    viewTransition: bool = DEFAULT,
    **props: Unpack[HTMLAnchorProps],
): ...


@react_component("Outlet", "react-router")
def Outlet(key: Optional[str] = None): ...


__all__ = ["Link", "Outlet"]
