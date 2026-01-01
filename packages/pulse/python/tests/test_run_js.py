"""Tests for run_js functionality."""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.render_session import RenderSession, run_js
from pulse.transpiler.function import javascript
from pulse.transpiler.id import next_id, reset_id_counter
from pulse.transpiler.nodes import Expr, emit


@dataclass
class SentJsExec:
	"""Record of a sent JS execution."""

	id: str
	code: str
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
					code=msg["code"],
					path=msg["path"],
				)
			)

	def run_js(
		self, expr: Expr | str, *, result: bool = False
	) -> asyncio.Future[object] | None:
		"""Mock implementation of RenderSession.run_js."""
		ctx = PulseContext.get()
		exec_id = next_id()

		if isinstance(expr, str):
			code = expr
		else:
			code = emit(expr)

		path = ctx.route.pathname if ctx.route else "/"

		self.send({"type": "js_exec", "path": path, "id": exec_id, "code": code})

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
	render: "RenderSession | Any",
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


class TestRunJs:
	def test_run_js_requires_context(self) -> None:
		"""run_js should raise when called outside callback context."""
		with pytest.raises(RuntimeError, match="can only be called during callback"):
			run_js("console.log('test')")

	def test_run_js_fire_and_forget(self) -> None:
		"""run_js without result=True should return None."""
		mock = MockRenderSession()
		with set_render_context(mock):
			result = run_js("console.log('hello')")

			assert result is None
			assert len(mock.sent_commands) == 1
			assert mock.sent_commands[0].code == "console.log('hello')"
			assert mock.sent_commands[0].path == "/"
			# No future registered
			assert len(mock.pending_js_results) == 0

	@pytest.mark.asyncio
	async def test_run_js_with_result(self) -> None:
		"""run_js with result=True should return a Future."""
		mock = MockRenderSession()
		with set_render_context(mock):
			future = run_js("return 42", result=True)

			assert isinstance(future, asyncio.Future)
			assert len(mock.sent_commands) == 1
			# Future registered for result
			assert len(mock.pending_js_results) == 1
			assert mock.sent_commands[0].id in mock.pending_js_results

	def test_run_js_with_js_function(self) -> None:
		"""run_js with a @javascript function call should emit code."""

		@javascript
		def greet(name: str) -> str:
			return f"Hello, {name}!"

		mock = MockRenderSession()
		with set_render_context(mock):
			run_js(greet("World"))

			assert len(mock.sent_commands) == 1
			code = mock.sent_commands[0].code
			# Should call the greet function with "World"
			assert "greet_" in code
			assert '"World"' in code

	def test_multiple_run_js_calls(self) -> None:
		"""Multiple run_js calls should send multiple commands."""
		mock = MockRenderSession()
		with set_render_context(mock):
			run_js("console.log(1)")
			run_js("console.log(2)")
			run_js("console.log(3)")

			assert len(mock.sent_commands) == 3
			assert mock.sent_commands[0].id == "1"
			assert mock.sent_commands[1].id == "2"
			assert mock.sent_commands[2].id == "3"

	def test_run_js_uses_route_path(self) -> None:
		"""run_js should use the pathname from the route context."""
		mock = MockRenderSession()
		with set_render_context(mock, pathname="/dashboard"):
			run_js("console.log('test')")

			assert mock.sent_commands[0].path == "/dashboard"


class TestRunJsWithResult:
	@pytest.mark.asyncio
	async def test_result_future_can_be_resolved(self) -> None:
		"""The returned future should be resolvable."""
		mock = MockRenderSession()
		with set_render_context(mock):
			future = run_js("return 42", result=True)

			# Simulate the result coming back
			exec_id = mock.sent_commands[0].id
			mock.pending_js_results[exec_id].set_result(42)

			result = await future
			assert result == 42
