import asyncio
import threading

import pulse as ps
import pytest
from anyio import to_thread
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.scheduling import TaskRegistry, TimerRegistry, call_soon, create_task
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

	task = registry.create_task(work(), name="test.task")
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

	task = registry.create_task(work(), name="test.cancel")
	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	registry.cancel_all()

	assert len(registry._tasks) == 0  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)
	assert task.cancelled()


@pytest.mark.asyncio
async def test_timer_registry_later_runs_sync_and_discards():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
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
async def test_timer_registry_later_from_anyio_worker_thread_runs_on_loop():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	fired = asyncio.Event()

	def callback():
		fired.set()

	handle = await to_thread.run_sync(lambda: registry.later(0.01, callback))

	assert handle in registry._handles  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_timer_registry_later_from_anyio_worker_thread_can_cancel():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	fired = False

	def callback():
		nonlocal fired
		fired = True

	handle = await to_thread.run_sync(lambda: registry.later(0.05, callback))

	assert handle in registry._handles  # pyright: ignore[reportPrivateUsage]
	handle.cancel()
	await asyncio.sleep(0.1)

	assert fired is False
	assert len(registry._handles) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_timer_registry_later_from_anyio_worker_thread_can_cancel_in_worker():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	fired = False

	def callback():
		nonlocal fired
		fired = True

	def schedule_and_cancel():
		handle = registry.later(0.05, callback)
		handle.cancel()

	await to_thread.run_sync(schedule_and_cancel)
	assert await wait_for(
		lambda: len(registry._handles) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)
	await asyncio.sleep(0.1)

	assert fired is False


@pytest.mark.asyncio
async def test_timer_registry_repeat_from_anyio_worker_thread_runs():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	fired = asyncio.Event()
	count = 0

	def callback():
		nonlocal count
		count += 1
		if count >= 2:
			fired.set()

	handle = await to_thread.run_sync(lambda: registry.repeat(0.01, callback))

	assert handle.task is not None
	await wait_for(lambda: fired.is_set(), timeout=0.2)
	handle.cancel()
	finished_count = count
	await asyncio.sleep(0.05)

	assert count == finished_count


@pytest.mark.asyncio
async def test_timer_registry_repeat_can_cancel_from_anyio_worker_thread():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	fired = asyncio.Event()
	count = 0

	def callback():
		nonlocal count
		count += 1
		if count >= 2:
			fired.set()

	handle = registry.repeat(0.01, callback)

	await wait_for(lambda: fired.is_set(), timeout=0.2)
	await to_thread.run_sync(handle.cancel)
	finished_count = count
	await asyncio.sleep(0.05)

	assert count == finished_count


@pytest.mark.asyncio
async def test_timer_registry_later_and_repeat_from_bare_thread_run_on_loop():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	tasks.bind_loop(asyncio.get_running_loop())
	registry.bind_loop(asyncio.get_running_loop())
	later_fired = asyncio.Event()
	repeat_fired = asyncio.Event()
	callback_thread_ids: list[int] = []
	repeat_count = 0
	handles = []

	def later_callback():
		callback_thread_ids.append(threading.get_ident())
		later_fired.set()

	def repeat_callback():
		nonlocal repeat_count
		repeat_count += 1
		if repeat_count >= 2:
			repeat_fired.set()

	def schedule():
		handles.append(registry.later(0.01, later_callback))
		handles.append(registry.repeat(0.01, repeat_callback))

	thread = threading.Thread(target=schedule)
	thread.start()
	await asyncio.to_thread(thread.join)

	assert await wait_for(lambda: later_fired.is_set(), timeout=0.2)
	assert await wait_for(lambda: repeat_fired.is_set(), timeout=0.2)
	assert callback_thread_ids == [threading.get_ident()]

	handles[1].cancel()
	finished_count = repeat_count
	await asyncio.sleep(0.05)
	assert repeat_count == finished_count


@pytest.mark.asyncio
async def test_timer_registry_later_and_repeat_from_asyncio_worker_thread_run_on_loop():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
	loop = asyncio.get_running_loop()
	tasks.bind_loop(loop)
	registry.bind_loop(loop)
	later_fired = asyncio.Event()
	repeat_fired = asyncio.Event()
	repeat_count = 0

	def later_callback():
		later_fired.set()

	def repeat_callback():
		nonlocal repeat_count
		repeat_count += 1
		if repeat_count >= 2:
			repeat_fired.set()

	def schedule():
		return (
			registry.later(0.01, later_callback),
			registry.repeat(0.01, repeat_callback),
		)

	later_handle, repeat_handle = await asyncio.to_thread(schedule)

	assert await wait_for(lambda: later_fired.is_set(), timeout=0.2)
	assert await wait_for(lambda: repeat_fired.is_set(), timeout=0.2)
	repeat_handle.cancel()
	finished_count = repeat_count
	await asyncio.sleep(0.05)
	assert repeat_count == finished_count
	later_handle.cancel()


@pytest.mark.asyncio
async def test_timer_registry_thread_scheduling_requires_bound_loop():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")

	with pytest.raises(RuntimeError, match="test registry has no bound loop"):
		await asyncio.to_thread(registry.later, 0.01, lambda: None)


@pytest.mark.asyncio
async def test_timer_registry_later_runs_async_and_discards():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
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
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
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
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")

	def callback():
		return None

	handle = registry.later(10, callback)
	assert len(registry._handles) == 1  # pyright: ignore[reportPrivateUsage]

	handle.cancel()

	assert len(registry._handles) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_timer_registry_cancel_all_cancels_and_clears():
	tasks = TaskRegistry(name="tasks")
	registry = TimerRegistry(tasks=tasks, name="test")
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
async def test_create_task_tracks_render_task_and_cancels_on_close():
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

	with ps.PulseContext.update(render=session):
		task = create_task(work())

	assert task in session._tasks._tasks  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	session.close()

	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_call_soon_tracks_render_task_and_cancels_on_close():
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
		call_soon(callback)

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
