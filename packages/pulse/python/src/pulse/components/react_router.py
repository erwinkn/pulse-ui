"""React Router components for client-side navigation.

Provides Pulse bindings for react-router's Link and Outlet components.
"""

from typing import Literal, TypedDict, Unpack

from pulse.dom.props import HTMLAnchorProps
from pulse.transpiler import Import
from pulse.transpiler.nodes import Node
from pulse.transpiler.react_component import react_component


class LinkPath(TypedDict):
	"""TypedDict for Link's `to` prop when using an object instead of string."""

	pathname: str
	search: str
	hash: str


# @react_component(Import("Link", "react-router", version="^7"))
@react_component(Import("Link", "react-router"))
def Link(
	*children: Node,
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
) -> None:
	"""Client-side navigation link using react-router.

	Renders an anchor tag that performs client-side navigation without a full
	page reload. Supports prefetching and various navigation behaviors.

	Args:
		*children: Content to render inside the link.
		key: React reconciliation key.
		to: The target URL path (e.g., "/dashboard", "/users/123").
		discover: Route discovery behavior. "render" discovers on render,
			"none" disables discovery.
		prefetch: Prefetch strategy. "intent" (default) prefetches on hover/focus,
			"render" prefetches immediately, "viewport" when visible, "none" disables.
		preventScrollReset: If True, prevents scroll position reset on navigation.
		relative: Path resolution mode. "route" resolves relative to route hierarchy,
			"path" resolves relative to URL path.
		reloadDocument: If True, performs a full page navigation instead of SPA.
		replace: If True, replaces current history entry instead of pushing.
		state: Arbitrary state to pass to the destination location.
		viewTransition: If True, enables View Transitions API for the navigation.
		**props: Additional HTML anchor attributes (className, onClick, etc.).

	Example:
		Basic navigation::

			ps.Link(to="/dashboard")["Go to Dashboard"]

		With prefetching disabled::

			ps.Link(to="/settings", prefetch="none")["Settings"]
	"""
	...


# @react_component(Import("Outlet", "react-router", version="^7"))
@react_component(Import("Outlet", "react-router"))
def Outlet(key: str | None = None) -> None:
	"""Renders the matched child route's element.

	Outlet is used in parent route components to render their child routes.
	It acts as a placeholder where nested route content will be displayed.

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
