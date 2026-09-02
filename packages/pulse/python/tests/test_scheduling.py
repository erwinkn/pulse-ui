import asyncio
import threading

import pulse as ps
import pytest
from anyio import to_thread
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.scheduling import Scheduler, call_soon, create_task
from pulse.test_helpers import wait_for
from pulse.user_session import UserSession


@ps.component
def simple_component():
	return ps.div()


@pytest.mark.asyncio
async def test_scheduler_tracks_and_discards_tasks_on_done():
	scheduler = Scheduler(name="test")
	started = asyncio.Event()
	finished = asyncio.Event()

	async def work():
		started.set()
		await asyncio.sleep(0)
		finished.set()
		return 1

	task = scheduler.create_task(work(), name="test.task")
	assert task in scheduler._tasks  # pyright: ignore[reportPrivateUsage]

	assert await wait_for(lambda: started.is_set(), timeout=0.2)
	assert await wait_for(lambda: finished.is_set(), timeout=0.2)
	assert await wait_for(
		lambda: len(scheduler._tasks) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)
	assert task.done()


@pytest.mark.asyncio
async def test_scheduler_cancel_tasks_cancels_and_clears():
	scheduler = Scheduler(name="test")
	started = asyncio.Event()
	cancelled = asyncio.Event()

	async def work():
		started.set()
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	task = scheduler.create_task(work(), name="test.cancel")
	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	scheduler.cancel_tasks()

	assert len(scheduler._tasks) == 0  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)
	assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_later_runs_sync_and_discards():
	scheduler = Scheduler(name="tasks")
	fired = False

	def callback():
		nonlocal fired
		fired = True

	scheduler.later(0.01, callback)

	assert await wait_for(lambda: fired, timeout=0.2)
	assert await wait_for(
		lambda: len(scheduler._timers) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)


@pytest.mark.asyncio
async def test_scheduler_later_from_anyio_worker_thread_runs_on_loop():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
	fired = asyncio.Event()

	def callback():
		fired.set()

	handle = await to_thread.run_sync(lambda: scheduler.later(0.01, callback))

	assert handle in scheduler._timers  # pyright: ignore[reportPrivateUsage]
	assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_later_from_anyio_worker_thread_can_cancel():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
	fired = False

	def callback():
		nonlocal fired
		fired = True

	handle = await to_thread.run_sync(lambda: scheduler.later(0.05, callback))

	assert handle in scheduler._timers  # pyright: ignore[reportPrivateUsage]
	handle.cancel()
	await asyncio.sleep(0.1)

	assert fired is False
	assert len(scheduler._timers) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_scheduler_later_from_anyio_worker_thread_can_cancel_in_worker():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
	fired = False

	def callback():
		nonlocal fired
		fired = True

	def schedule_and_cancel():
		handle = scheduler.later(0.05, callback)
		handle.cancel()

	await to_thread.run_sync(schedule_and_cancel)
	assert await wait_for(
		lambda: len(scheduler._timers) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)
	await asyncio.sleep(0.1)

	assert fired is False


@pytest.mark.asyncio
async def test_scheduler_repeat_from_anyio_worker_thread_runs():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
	fired = asyncio.Event()
	count = 0

	def callback():
		nonlocal count
		count += 1
		if count >= 2:
			fired.set()

	handle = await to_thread.run_sync(lambda: scheduler.repeat(0.01, callback))

	assert handle.task is not None
	await wait_for(lambda: fired.is_set(), timeout=0.2)
	handle.cancel()
	finished_count = count
	await asyncio.sleep(0.05)

	assert count == finished_count


@pytest.mark.asyncio
async def test_scheduler_repeat_can_cancel_from_anyio_worker_thread():
	scheduler = Scheduler(name="tasks")
	fired = asyncio.Event()
	count = 0

	def callback():
		nonlocal count
		count += 1
		if count >= 2:
			fired.set()

	handle = scheduler.repeat(0.01, callback)

	await wait_for(lambda: fired.is_set(), timeout=0.2)
	await to_thread.run_sync(handle.cancel)
	finished_count = count
	await asyncio.sleep(0.05)

	assert count == finished_count


@pytest.mark.asyncio
async def test_scheduler_later_and_repeat_from_bare_thread_run_on_loop():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
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
		handles.append(scheduler.later(0.01, later_callback))
		handles.append(scheduler.repeat(0.01, repeat_callback))

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
async def test_scheduler_later_and_repeat_from_asyncio_worker_thread_run_on_loop():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
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
			scheduler.later(0.01, later_callback),
			scheduler.repeat(0.01, repeat_callback),
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
async def test_scheduler_worker_with_idle_loop_runs_on_bound_loop():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())
	fired = asyncio.Event()

	def callback():
		fired.set()

	def schedule():
		worker_loop = asyncio.new_event_loop()
		asyncio.set_event_loop(worker_loop)
		try:
			scheduler.later(0.01, callback)
		finally:
			asyncio.set_event_loop(None)
			worker_loop.close()

	await asyncio.to_thread(schedule)
	assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_different_running_loop_raises():
	scheduler = Scheduler(name="tasks")
	scheduler.bind(asyncio.get_running_loop())

	def schedule():
		async def run():
			scheduler.later(0.01, lambda: None)

		asyncio.run(run())

	with pytest.raises(
		RuntimeError,
		match="different event loop",
	):
		await asyncio.to_thread(schedule)


@pytest.mark.asyncio
async def test_scheduler_thread_scheduling_requires_bound_loop():
	def schedule():
		scheduler = Scheduler(name="tasks")
		scheduler.later(0.01, lambda: None)

	with pytest.raises(RuntimeError, match="tasks has no bound event loop"):
		await asyncio.to_thread(schedule)


@pytest.mark.asyncio
async def test_render_session_scheduling_before_first_loop_use_raises_off_loop():
	app = ps.App()
	app.server_address = "http://testserver"
	session = UserSession("test-session", {}, app)
	app.user_sessions[session.sid] = session

	async with app.fastapi.router.lifespan_context(app.fastapi):
		render = app.create_render("test-render", session)

		with pytest.raises(RuntimeError, match="no bound event loop"):
			await asyncio.to_thread(render.schedule_later, 0.01, lambda: None)


@pytest.mark.asyncio
async def test_render_session_binds_its_scheduler_on_first_scheduling():
	app = ps.App()
	app.server_address = "http://testserver"
	session = UserSession("test-session", {}, app)
	app.user_sessions[session.sid] = session
	fired = asyncio.Event()

	async with app.fastapi.router.lifespan_context(app.fastapi):
		render = app.create_render("test-render", session)
		assert render.scheduler is not app.scheduler
		assert render.scheduler.loop is None
		render.schedule_later(0.01, lambda: None)
		assert render.scheduler.loop is asyncio.get_running_loop()

		await asyncio.to_thread(render.schedule_later, 0.01, fired.set)
		assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_later_runs_async_and_discards():
	scheduler = Scheduler(name="tasks")
	fired = asyncio.Event()

	async def callback():
		await asyncio.sleep(0)
		fired.set()

	scheduler.later(0.01, callback)

	assert await wait_for(lambda: fired.is_set(), timeout=0.2)
	assert await wait_for(
		lambda: len(scheduler._timers) == 0,  # pyright: ignore[reportPrivateUsage]
		timeout=0.2,
	)


@pytest.mark.asyncio
async def test_scheduler_later_runs_coroutine_return():
	scheduler = Scheduler(name="tasks")
	fired = asyncio.Event()

	async def inner():
		await asyncio.sleep(0)
		fired.set()

	def callback():
		return inner()

	scheduler.later(0.01, callback)

	assert await wait_for(lambda: fired.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_cancel_discards_timer_handle():
	scheduler = Scheduler(name="tasks")

	def callback():
		return None

	handle = scheduler.later(10, callback)
	assert len(scheduler._timers) == 1  # pyright: ignore[reportPrivateUsage]

	handle.cancel()

	assert len(scheduler._timers) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_scheduler_cancel_timers_cancels_and_clears():
	scheduler = Scheduler(name="tasks")
	fired = False

	def callback():
		nonlocal fired
		fired = True

	scheduler.later(0.05, callback)
	scheduler.later(0.05, callback)
	scheduler.cancel_timers()

	assert len(scheduler._timers) == 0  # pyright: ignore[reportPrivateUsage]
	await asyncio.sleep(0.1)
	assert fired is False


@pytest.mark.asyncio
async def test_scheduler_cancel_all_cancels_timers_and_tasks():
	scheduler = Scheduler(name="test")
	timer_fired = False

	def callback():
		nonlocal timer_fired
		timer_fired = True

	scheduler.later(0.01, callback)
	task = scheduler.create_task(asyncio.sleep(10))
	scheduler.cancel_all()
	await asyncio.sleep(0.1)

	assert timer_fired is False
	assert task.cancelled()
	assert len(scheduler._timers) == 0  # pyright: ignore[reportPrivateUsage]
	assert len(scheduler._tasks) == 0  # pyright: ignore[reportPrivateUsage]


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

	assert task in session.scheduler._tasks  # pyright: ignore[reportPrivateUsage]
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
	assert task in session.scheduler._tasks  # pyright: ignore[reportPrivateUsage]

	session.close()

	assert await wait_for(lambda: task.done(), timeout=0.2)


@pytest.mark.asyncio
async def test_later_uses_app_scheduler_without_render():
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
