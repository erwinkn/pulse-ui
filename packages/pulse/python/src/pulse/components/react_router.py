from typing import Unpack

from pulse.dom.props import HTMLAnchorProps
from pulse.transpiler import Import
from pulse.transpiler.nodes import Node
from pulse.transpiler.react_component import react_component


# Link component from custom Pulse router (no react-router dependency)
@react_component(Import("Link", "pulse-ui-client"))
def Link(
	*children: Node,
	key: str | None = None,
	to: str,
	prefetch: bool = True,
	replace: bool | None = None,
	state: dict[str, object] | None = None,
	**props: Unpack[HTMLAnchorProps],
): ...


# Outlet is a placeholder that gets substituted during VDOM rendering
# It's detected by _is_outlet() in render_session.py which checks for this import
# Using "__pulse_internal__/Outlet" as a marker that won't be treated as an npm dependency
@react_component(Import("Outlet", "__pulse_internal__/Outlet"))
def Outlet(key: str | None = None): ...


__all__ = ["Link", "Outlet"]
