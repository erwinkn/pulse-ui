import asyncio

import pytest
from pulse.scheduling import TaskRegistry, TimerRegistry
from pulse.test_helpers import wait_for


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
