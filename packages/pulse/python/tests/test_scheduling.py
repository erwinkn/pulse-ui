import asyncio

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.scheduling import TaskRegistry, TimerRegistry
from pulse.test_helpers import wait_for


@ps.component
def simple_component():
	return ps.div()


@pytest.mark.asyncio
async def test_task_registry_tracks_and_discards_on_done():
	registry = TaskRegistry(name="test")
	started = asyncio.Event()
	finished = asyncio.Event()

	async def work():
		started.set()
		await asyncio.sleep(0)
		finished.set()
		return 1

	task = registry.create(work(), name="test.task")
	assert task in registry._tasks  # pyright: ignore[reportPrivateUsage]

	assert await wait_for(lambda: started.is_set(), timeout=0.2)
	assert await wait_for(lambda: finished.is_set(), timeout=0.2)
	assert await wait_for(
		lambda: len(registry._tasks) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)
	assert task.done()


@pytest.mark.asyncio
async def test_task_registry_cancel_all_cancels_and_clears():
	registry = TaskRegistry(name="test")
	started = asyncio.Event()
	cancelled = asyncio.Event()

	async def work():
		started.set()
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	task = registry.create(work(), name="test.cancel")
	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	registry.cancel_all()

	assert len(registry._tasks) == 0  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)
	assert task.cancelled()


@pytest.mark.asyncio
async def test_timer_registry_later_runs_sync_and_discards():
	registry = TimerRegistry(name="test")
	fired = False

	def callback():
		nonlocal fired
		fired = True

	registry.later(0.01, callback)

	assert await wait_for(lambda: fired, timeout=0.2)
	assert await wait_for(
		lambda: len(registry._handles) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)


@pytest.mark.asyncio
async def test_timer_registry_later_runs_async_and_discards():
	registry = TimerRegistry(name="test")
	fired = asyncio.Event()

	async def callback():
		await asyncio.sleep(0)
		fired.set()

	registry.later(0.01, callback)

	assert await wait_for(lambda: fired.is_set(), timeout=0.2)
	assert await wait_for(
		lambda: len(registry._handles) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)


@pytest.mark.asyncio
async def test_timer_registry_later_runs_coroutine_return():
	registry = TimerRegistry(name="test")
	fired = asyncio.Event()

	async def inner():
		await asyncio.sleep(0)
		fired.set()

	def callback():
		return inner()

	registry.later(0.01, callback)

	assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_timer_registry_cancel_discards_handle():
	registry = TimerRegistry(name="test")

	def callback():
		return None

	handle = registry.later(10, callback)
	assert len(registry._handles) == 1  # pyright: ignore[reportPrivateUsage]

	handle.cancel()

	assert len(registry._handles) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_timer_registry_cancel_all_cancels_and_clears():
	registry = TimerRegistry(name="test")
	fired = False

	def callback():
		nonlocal fired
		fired = True

	registry.later(0.05, callback)
	registry.later(0.05, callback)
	registry.cancel_all()

	assert len(registry._handles) == 0  # pyright: ignore[reportPrivateUsage]
	await asyncio.sleep(0.1)
	assert fired is False


@pytest.mark.asyncio
async def test_later_tracks_render_tasks_and_cancels_on_close():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	started = asyncio.Event()
	cancelled = asyncio.Event()

	async def work():
		started.set()
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	def callback():
		return work()

	with ps.PulseContext.update(render=session):
		ps.later(0.01, callback)

	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	session.close()

	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_repeat_tracks_render_task_and_cancels_on_close():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		handle = ps.repeat(10, lambda: None)

	task = handle.task
	assert task is not None
	assert (
		task in session._tasks._tasks  # pyright: ignore[reportPrivateUsage]
	)

	session.close()

	assert await wait_for(lambda: task.done(), timeout=0.2)


@pytest.mark.asyncio
async def test_later_uses_app_registry_without_render():
	app = ps.PulseContext.get().app
	started = asyncio.Event()
	cancelled = asyncio.Event()

	async def work():
		started.set()
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	def callback():
		return work()

	ps.later(0.01, callback)

	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	await app.close()

	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)
