from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import RouteTree

P = ParamSpec("P")
R = TypeVar("R")


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	"""Set up a PulseContext with an App for all tests."""
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def with_render_session(fn: Callable[P, Awaitable[R]]):
	"""Decorator to wrap test functions with a RenderSession context."""

	async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
		# Create a minimal RouteTree for the session (not needed for mutation tests)
		routes = RouteTree([])
		session = RenderSession("test-session", routes)
		with ps.PulseContext.update(render=session):
			return await fn(*args, **kwargs)

	return wrapper


@pytest.mark.asyncio
@with_render_session
async def test_mutation_basic_execution():
	"""Test basic mutation execution and result properties."""

	class S(ps.State):
		value: int = 0

		@ps.mutation
		async def increment(self, amount: int) -> int:
			self.value += amount
			return self.value

	s = S()
	mutation = s.increment

	# Initially not running, no data, no error
	assert mutation.is_running is False
	assert mutation.data is None
	assert mutation.error is None

	# Execute mutation
	result = await mutation(5)

	# Check result
	assert result == 5
	assert s.value == 5

	# Check mutation state after execution
	assert mutation.is_running is False
	assert mutation.data == 5
	assert mutation.error is None


@pytest.mark.asyncio
@with_render_session
async def test_mutation_error_handling():
	"""Test mutation error handling."""

	class S(ps.State):
		@ps.mutation
		async def failing_mutation(self) -> str:
			raise ValueError("Test error")

	s = S()
	mutation = s.failing_mutation

	# Execute mutation that fails
	with pytest.raises(ValueError, match="Test error"):
		await mutation()

	# Check mutation state after error
	assert mutation.is_running is False
	assert mutation.data is None
	assert isinstance(mutation.error, ValueError)
	assert str(mutation.error) == "Test error"


@pytest.mark.asyncio
@with_render_session
async def test_mutation_on_success_callback():
	"""Test on_success callback."""

	smuggled_data = None  # Will be made nonlocal in callback

	class S(ps.State):
		@ps.mutation
		async def success_mutation(self) -> str:
			return "success"

		@success_mutation.on_success
		def _on_success(self, data: str):
			nonlocal smuggled_data
			smuggled_data = data

	s = S()
	result = await s.success_mutation()

	assert result == "success"
	assert smuggled_data == "success"


@pytest.mark.asyncio
@with_render_session
async def test_mutation_on_error_callback():
	"""Test on_error callback."""

	smuggled_error = None  # Will be made nonlocal in callback

	class S(ps.State):
		@ps.mutation
		async def error_mutation(self) -> str:
			raise RuntimeError("Test error")

		@error_mutation.on_error
		def _on_error(self, e: Exception):
			nonlocal smuggled_error
			smuggled_error = e

	s = S()

	with pytest.raises(RuntimeError, match="Test error"):
		await s.error_mutation()

	assert isinstance(smuggled_error, RuntimeError)
	assert str(smuggled_error) == "Test error"


@pytest.mark.asyncio
@with_render_session
async def test_mutation_multiple_calls():
	"""Test multiple calls to the same mutation."""

	class S(ps.State):
		call_count: int = 0

		@ps.mutation
		async def counter_mutation(self) -> int:
			self.call_count += 1
			return self.call_count

	s = S()
	mutation = s.counter_mutation

	# First call
	result1 = await mutation()
	assert result1 == 1
	assert mutation.data == 1

	# Second call
	result2 = await mutation()
	assert result2 == 2
	assert mutation.data == 2

	# Third call
	result3 = await mutation()
	assert result3 == 3
	assert mutation.data == 3


@pytest.mark.asyncio
@with_render_session
async def test_mutation_is_running_state():
	"""Test that is_running is properly set during execution."""

	import asyncio

	running_states = []

	class S(ps.State):
		@ps.mutation
		async def slow_mutation(self) -> str:
			running_states.append(self.slow_mutation.is_running)
			await asyncio.sleep(0.01)
			running_states.append(self.slow_mutation.is_running)
			return "done"

	s = S()
	mutation = s.slow_mutation

	# Start mutation
	task = asyncio.create_task(mutation())

	# Check that it's running
	await asyncio.sleep(0.005)
	assert mutation.is_running is True

	# Wait for completion
	result = await task
	assert result == "done"
	assert mutation.is_running is False

	# Check running states were captured correctly
	assert running_states == [True, True]


@pytest.mark.asyncio
@with_render_session
async def test_mutation_with_parameters():
	"""Test mutation with parameters."""

	class S(ps.State):
		total: int = 0

		@ps.mutation
		async def add_values(self, a: int, b: int, multiplier: int = 1) -> int:
			result = (a + b) * multiplier
			self.total += result
			return result

	s = S()
	mutation = s.add_values

	# Call with positional args
	result1 = await mutation(2, 3)
	assert result1 == 5
	assert s.total == 5

	# Call with keyword args
	result2 = await mutation(1, 2, multiplier=3)
	assert result2 == 9
	assert s.total == 14

	# Check data property
	assert mutation.data == 9
