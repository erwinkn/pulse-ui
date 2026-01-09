"""Python-side ErrorBoundary component for catching rendering errors."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from pulse.env import env
from pulse.transpiler.nodes import Element, Node


class RenderError:
	"""Error information passed to fallback functions."""

	__slots__: tuple[str, ...] = ("message", "stack")

	message: str
	stack: str | None

	def __init__(self, message: str, stack: str | None = None) -> None:
		self.message = message
		self.stack = stack

	@staticmethod
	def from_exception(exc: BaseException) -> RenderError:
		"""Create a RenderError from an exception."""
		message = str(exc)
		if not message:
			message = type(exc).__name__
		stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
		return RenderError(message, stack)


# Type alias for fallback functions
FallbackFn = Callable[[RenderError], Node]


def default_fallback(error: RenderError) -> Element:
	"""Default fallback UI for ErrorBoundary.

	Shows error message and stack trace (dev mode only).
	Matches the visual style of the React DefaultErrorFallback component.
	"""
	is_dev = env.pulse_env == "dev"

	children: list[Node] = [
		Element(
			tag="h2",
			props={"style": {"margin": "0 0 10px 0", "fontSize": "18px"}},
			children=["Something went wrong"],
		),
		Element(
			tag="p",
			props={"style": {"margin": "0 0 15px 0", "fontSize": "14px"}},
			children=[error.message],
		),
	]

	if is_dev and error.stack:
		children.append(
			Element(
				tag="pre",
				props={
					"style": {
						"margin": "0 0 15px 0",
						"padding": "10px",
						"backgroundColor": "#fed7d7",
						"borderRadius": "4px",
						"fontSize": "12px",
						"overflow": "auto",
						"whiteSpace": "pre-wrap",
						"wordBreak": "break-word",
					}
				},
				children=[error.stack],
			)
		)

	return Element(
		tag="div",
		props={
			"style": {
				"padding": "20px",
				"border": "1px solid #e53e3e",
				"borderRadius": "8px",
				"backgroundColor": "#fff5f5",
				"color": "#c53030",
				"fontFamily": "system-ui, sans-serif",
			}
		},
		children=children,
	)


class ErrorBoundary:
	"""Python-side ErrorBoundary for catching rendering errors.

	Catches errors during VDOM rendering of children and renders
	a fallback UI instead of propagating the error.

	Args:
		*children: Child nodes to render
		fallback: Server-side fallback function receiving (error: RenderError) -> Node
		client_fallback: Client-side fallback for React ErrorBoundary (passed through to JS)

	Example:
		ErrorBoundary(
			MyComponent(),
			fallback=lambda error: div(f"Error: {error.message}"),
		)
	"""

	__slots__: tuple[str, ...] = ("children", "fallback", "client_fallback", "_error")

	children: tuple[Any, ...]
	fallback: FallbackFn | None
	client_fallback: Any  # Passed to client React ErrorBoundary
	_error: RenderError | None

	def __init__(
		self,
		*children: Any,
		fallback: FallbackFn | None = None,
		client_fallback: Any = None,
	) -> None:
		self.children = children
		self.fallback = fallback
		self.client_fallback = client_fallback
		self._error = None

	def render_children(self) -> Node:
		"""Render children with error catching.

		This method is called by the renderer to get the VDOM.
		If an error occurs during rendering, the fallback is used instead.
		"""
		from pulse.renderer import RenderTree

		# Return children directly if there's only one, otherwise wrap in fragment
		if len(self.children) == 1:
			child = self.children[0]
		else:
			child = Element(tag="", children=list(self.children))

		try:
			# Test render to catch errors
			tree = RenderTree(child)
			tree.render()
			# No error - return children for actual rendering
			return child
		except Exception as exc:
			self._error = RenderError.from_exception(exc)
			fallback_fn = self.fallback or default_fallback
			return fallback_fn(self._error)

	@property
	def error(self) -> RenderError | None:
		"""Get the captured error, if any."""
		return self._error
