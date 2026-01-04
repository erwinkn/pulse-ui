"""Tests for run_js functionality."""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.js import console
from pulse.render_session import run_js
from pulse.transpiler.function import javascript
from pulse.transpiler.id import next_id, reset_id_counter
from pulse.transpiler.nodes import Expr
from pulse.transpiler.vdom import VDOMNode


@dataclass
class SentJsExec:
	"""Record of a sent JS execution."""

	id: str
	expr: VDOMNode
	path: str


class MockRenderSession:
	"""Mock RenderSession for testing run_js."""

	def __init__(self) -> None:
		self.sent_commands: list[SentJsExec] = []
		self._pending_js_results: dict[str, asyncio.Future[object]] = {}

	@property
	def pending_js_results(self):
		return self._pending_js_results

	def send(self, msg: dict[str, Any]) -> None:
		"""Mock send that captures js_exec messages."""
		if msg.get("type") == "js_exec":
			self.sent_commands.append(
				SentJsExec(
					id=msg["id"],
					expr=msg["expr"],
					path=msg["path"],
				)
			)

	def run_js(
		self, expr: Expr, *, result: bool = False
	) -> asyncio.Future[object] | None:
		"""Mock implementation of RenderSession.run_js."""
		ctx = PulseContext.get()
		exec_id = next_id()

		path = ctx.route.pathname if ctx.route else "/"

		self.send(
			{"type": "js_exec", "path": path, "id": exec_id, "expr": expr.render()}
		)

		if result:
			loop = asyncio.get_running_loop()
			future: asyncio.Future[object] = loop.create_future()
			self._pending_js_results[exec_id] = future
			return future

		return None


@dataclass
class MockRoute:
	"""Mock route for testing."""

	pathname: str = "/"


@contextmanager
def set_render_context(
	render: Any,
	pathname: str = "/",
) -> Generator[None, None, None]:
	"""Set up PulseContext with a render session for testing."""
	mock_app = MagicMock()
	mock_route = MockRoute(pathname=pathname)
	ctx = PulseContext(app=mock_app, render=render, route=mock_route)  # pyright: ignore[reportArgumentType]
	token = PULSE_CONTEXT.set(ctx)
	try:
		yield
	finally:
		PULSE_CONTEXT.reset(token)


@pytest.fixture(autouse=True)
def _reset_ids():  # pyright: ignore[reportUnusedFunction]
	reset_id_counter()


# Define test functions
@javascript
def log_message(msg: str):
	console.log(msg)


@javascript
def greet(name: str) -> str:
	return f"Hello, {name}!"


@javascript
def get_value() -> int:
	return 42


class TestRunJs:
	def test_run_js_requires_context(self) -> None:
		"""run_js should raise when called outside callback context."""
		with pytest.raises(RuntimeError, match="can only be called during callback"):
			run_js(log_message("test"))  # pyright: ignore[reportArgumentType]

	def test_run_js_fire_and_forget(self) -> None:
		"""run_js without result=True should return None."""
		mock = MockRenderSession()
		with set_render_context(mock):
			result = run_js(log_message("hello"))  # pyright: ignore[reportArgumentType]

			assert result is None
			assert len(mock.sent_commands) == 1
			# Expr should be a CallExpr
			expr = mock.sent_commands[0].expr
			assert isinstance(expr, dict) and expr.get("t") == "call"
			assert mock.sent_commands[0].path == "/"
			# No future registered
			assert len(mock.pending_js_results) == 0

	@pytest.mark.asyncio
	async def test_run_js_with_result(self) -> None:
		"""run_js with result=True should return a Future."""
		mock = MockRenderSession()
		with set_render_context(mock):
			future = run_js(get_value(), result=True)  # pyright: ignore[reportArgumentType,reportCallIssue]

			assert isinstance(future, asyncio.Future)
			assert len(mock.sent_commands) == 1
			# Future registered for result
			assert len(mock.pending_js_results) == 1
			assert mock.sent_commands[0].id in mock.pending_js_results

	def test_run_js_with_js_function(self) -> None:
		"""run_js with a @javascript function call should produce a CallExpr."""
		mock = MockRenderSession()
		with set_render_context(mock):
			run_js(greet("World"))  # pyright: ignore[reportArgumentType]

			assert len(mock.sent_commands) == 1
			expr = mock.sent_commands[0].expr
			# Should be a call expression
			assert isinstance(expr, dict) and expr.get("t") == "call"
			# Check that args contain "World"
			args = expr.get("args", [])
			assert len(args) == 1
			assert args[0] == "World"

	def test_multiple_run_js_calls(self) -> None:
		"""Multiple run_js calls should send multiple commands."""
		mock = MockRenderSession()
		with set_render_context(mock):
			run_js(log_message("1"))  # pyright: ignore[reportArgumentType]
			run_js(log_message("2"))  # pyright: ignore[reportArgumentType]
			run_js(log_message("3"))  # pyright: ignore[reportArgumentType]

			assert len(mock.sent_commands) == 3
			assert mock.sent_commands[0].id == "1"
			assert mock.sent_commands[1].id == "2"
			assert mock.sent_commands[2].id == "3"

	def test_run_js_uses_route_path(self) -> None:
		"""run_js should use the pathname from the route context."""
		mock = MockRenderSession()
		with set_render_context(mock, pathname="/dashboard"):
			run_js(log_message("test"))  # pyright: ignore[reportArgumentType]

			assert mock.sent_commands[0].path == "/dashboard"


class TestRunJsWithResult:
	@pytest.mark.asyncio
	async def test_result_future_can_be_resolved(self) -> None:
		"""The returned future should be resolvable."""
		mock = MockRenderSession()
		with set_render_context(mock):
			future = run_js(get_value(), result=True)  # pyright: ignore[reportArgumentType,reportCallIssue]

			# Simulate the result coming back
			exec_id = mock.sent_commands[0].id
			mock.pending_js_results[exec_id].set_result(42)

			result = await future
			assert result == 42
