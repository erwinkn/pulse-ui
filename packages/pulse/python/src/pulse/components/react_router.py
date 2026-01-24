"""Pulse router components for client-side navigation."""

from typing import Literal, Unpack

from pulse.dom.props import HTMLAnchorProps
from pulse.react_component import react_component
from pulse.transpiler import Import
from pulse.transpiler.nodes import Node


@react_component(Import("Link", "pulse-ui-client"))
def Link(
	*children: Node,
	key: str | None = None,
	to: str,
	prefetch: Literal["none", "intent", "render", "viewport"] = "intent",
	reloadDocument: bool | None = None,
	replace: bool | None = None,
	**props: Unpack[HTMLAnchorProps],
) -> None:
	"""Client-side navigation link.

	Renders an anchor tag that performs client-side navigation without a full
	page reload. Supports prefetching and various navigation behaviors.

	Args:
		*children: Content to render inside the link.
		key: React reconciliation key.
		to: The target URL path (e.g., "/dashboard", "/users/123").
		prefetch: Prefetch strategy. "intent" (default) prefetches on hover/focus,
			"render" prefetches immediately, "viewport" when visible, "none" disables.
		reloadDocument: If True, performs a full page navigation instead of SPA.
		replace: If True, replaces current history entry instead of pushing.
		**props: Additional HTML anchor attributes (className, onClick, etc.).

	Example:
		Basic navigation::

			ps.Link(to="/dashboard")["Go to Dashboard"]

		With prefetching disabled::

			ps.Link(to="/settings", prefetch="none")["Settings"]
	"""
	...


@react_component(Import("Outlet", "pulse-ui-client"))
def Outlet(key: str | None = None) -> None:
	"""Renders the matched child route's element.

	Args:
		key: React reconciliation key.

	Example:
		Layout with outlet for child routes::

			@ps.component
			def Layout():
				return ps.div(
					ps.nav("Navigation"),
					ps.Outlet(),  # Child route renders here
				)
	"""
	...


__all__ = ["Link", "Outlet"]
