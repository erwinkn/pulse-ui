from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, final

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.renderer import RenderTree
from pulse.routing import RouteTree
from pulse.test_helpers import wait_for

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
async def test_factory_mutations_use_class_member_identity():
	successes: list[tuple[int, int]] = []
	errors: list[tuple[int, str]] = []

	def make_mutation(value: int, *, fails: bool = False):
		async def member(self: ps.State) -> int:
			if fails:
				raise RuntimeError(f"failure {value}")
			return value

		member.__name__ = "shared"
		descriptor = ps.mutation(member)

		@descriptor.on_success
		async def _success(  # pyright: ignore[reportUnusedFunction]
			self: ps.State,
		):
			successes.append((id(self), value))

		@descriptor.on_error
		async def _error(  # pyright: ignore[reportUnusedFunction]
			self: ps.State, error: Exception
		):
			errors.append((id(self), str(error)))

		return descriptor

	@final
	class S(ps.State):
		first = make_mutation(1)
		second = make_mutation(2)
		failing = make_mutation(3, fails=True)

	s = S()
	first = s.first
	second = s.second

	assert first is not second
	assert S.__dict__["first"].name == "first"
	assert S.__dict__["second"].name == "second"
	assert S.__dict__["failing"].name == "failing"
	assert await first() == 1
	assert await second() == 2
	with pytest.raises(RuntimeError, match="failure 3"):
		await s.failing()
	assert successes == [(id(s), 1), (id(s), 2)]
	assert errors == [(id(s), "failure 3")]


@pytest.mark.asyncio
@with_render_session
async def test_mutation_descriptor_inheritance_keeps_base_binding():
	def make_mutation():
		async def renamed(self: ps.State) -> str:
			return type(self).__name__

		renamed.__name__ = "shared"
		return ps.mutation(renamed)

	class Base(ps.State):
		item = make_mutation()  # pyright: ignore[reportUnannotatedClassAttribute]

	class Left(Base):
		pass

	class Right(Base):
		pass

	descriptor = Base.__dict__["item"]
	states = [Base(), Left(), Right()]
	results = [state.item for state in states]

	assert descriptor.name == "item"
	assert len({id(result) for result in results}) == 3
	assert [await result() for result in results] == ["Base", "Left", "Right"]


@pytest.mark.asyncio
@with_render_session
async def test_mutation_override_uses_defining_member_identity():
	class Base(ps.State):
		@ps.mutation
		async def item(self) -> int:
			return 1

	class Child(Base):
		@ps.mutation
		async def item(  # pyright: ignore[reportIncompatibleVariableOverride]
			self,
		) -> int:
			return await super().item() + 1

	state = Child()
	child = state.item
	assert await child() == 2
	base = super(Child, state).item

	assert child is not base
	assert child.data == 2
	assert base.data == 1


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
	assert await wait_for(lambda: mutation.is_running is True, timeout=0.2)

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


@pytest.mark.asyncio
@with_render_session
async def test_zero_arg_mutation_as_callback_does_not_receive_event():
	class S(ps.State):
		paused: bool = False

		@ps.mutation
		async def toggle_pause(self) -> None:
			self.paused = not self.paused

	s = S()
	tree = RenderTree(ps.div(ps.button(onClick=s.toggle_pause)["Toggle"]))
	tree.render()

	callback = tree.callbacks["0.onClick"]
	assert callback.n_args == 0
	assert callback.accepts_varargs is False

	event = ({"type": "click"},)
	await callback.fn(
		*(event if callback.accepts_varargs else event[: callback.n_args])
	)

	assert s.paused is True
