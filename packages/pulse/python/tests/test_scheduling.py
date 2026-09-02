import asyncio
import threading

import pulse as ps
import pytest
from anyio import to_thread
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.scheduling import Scheduler, Task
from pulse.test_helpers import wait_for


@ps.component
def simple_component():
	return ps.div()


@pytest.mark.asyncio
async def test_scheduler_creates_and_tracks_tasks():
	async with Scheduler("test") as scheduler:
		started = asyncio.Event()

		async def work():
			started.set()
			return 1

		task = scheduler.create_task(work(), name="test.task")
		assert isinstance(task, Task)
		assert task.name == "test.task"
		assert await task == 1
		assert started.is_set()
		assert task.done()


@pytest.mark.asyncio
async def test_scheduler_later_call_soon_and_repeat():
	async with Scheduler("test") as scheduler:
		events: list[str] = []
		repeated = asyncio.Event()

		def later_callback():
			events.append("later")

		def soon_callback():
			events.append("soon")

		def repeat_callback():
			events.append("repeat")
			repeated.set()

		scheduler.later(0.01, later_callback)
		scheduler.call_soon(soon_callback)
		repeat = scheduler.repeat(0.01, repeat_callback)
		await wait_for(lambda: repeated.is_set(), timeout=0.2)
		repeat.cancel()
		await asyncio.sleep(0)
		assert events[0] == "soon"
		assert "later" in events
		assert repeat.done() or repeat.cancelled()


@pytest.mark.asyncio
async def test_scheduler_runs_async_callbacks():
	async with Scheduler("test") as scheduler:
		fired = asyncio.Event()

		async def callback():
			await asyncio.sleep(0)
			fired.set()

		task = scheduler.later(0.01, callback)
		await task
		assert fired.is_set()


@pytest.mark.asyncio
async def test_scheduler_dispatches_from_worker_threads():
	async with Scheduler("test") as scheduler:
		fired = asyncio.Event()
		results: list[Task[None]] = []

		def callback():
			fired.set()

		await to_thread.run_sync(lambda: results.append(scheduler.call_soon(callback)))
		await asyncio.to_thread(lambda: results.append(scheduler.call_soon(callback)))

		thread = threading.Thread(
			target=lambda: results.append(scheduler.call_soon(callback))
		)
		thread.start()
		await asyncio.to_thread(thread.join)
		await wait_for(lambda: fired.is_set(), timeout=0.2)
		assert len(results) == 3


@pytest.mark.asyncio
async def test_scheduler_rejects_foreign_loop():
	async with Scheduler("test") as scheduler:

		async def schedule():
			with pytest.raises(RuntimeError, match="different event loop"):
				scheduler.call_soon(lambda: None)

		await asyncio.to_thread(lambda: asyncio.run(schedule()))


@pytest.mark.asyncio
async def test_scheduler_rejects_before_start_and_after_close():
	scheduler = Scheduler("test")
	with pytest.raises(RuntimeError, match="scheduler is not running"):
		scheduler.call_soon(lambda: None)
	await scheduler.start()
	await scheduler.close()
	with pytest.raises(RuntimeError, match="scheduler is not running"):
		scheduler.call_soon(lambda: None)


@pytest.mark.asyncio
async def test_scheduler_start_twice_and_close_twice():
	scheduler = Scheduler("test")
	await scheduler.start()
	with pytest.raises(RuntimeError, match="already running"):
		await scheduler.start()
	await scheduler.close()
	await scheduler.close()
	assert not scheduler.running


@pytest.mark.asyncio
async def test_scheduler_cancel_before_first_tick():
	async with Scheduler("test") as scheduler:
		fired = False

		def callback():
			nonlocal fired
			fired = True

		task = scheduler.later(0.01, callback)
		task.cancel()
		await asyncio.sleep(0.05)
		assert not fired
		assert task.cancelled()


@pytest.mark.asyncio
async def test_task_cancel_from_thread():
	async with Scheduler("test") as scheduler:
		task = scheduler.create_task(asyncio.sleep(10))
		thread = threading.Thread(target=task.cancel)
		thread.start()
		await asyncio.to_thread(thread.join)
		with pytest.raises(asyncio.CancelledError):
			await task
		assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_close_drains_cancelled_tasks():
	scheduler = Scheduler("test")
	await scheduler.start()
	cancelled = asyncio.Event()

	async def work():
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	task = scheduler.create_task(work())
	await asyncio.sleep(0)
	await scheduler.close()
	assert cancelled.is_set()
	assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_isolates_task_exceptions():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		scheduler.create_task(_raise(ValueError("task")))
		survivor = scheduler.create_task(asyncio.sleep(0.02))
		await survivor
		await asyncio.sleep(0)
		assert contexts
		assert isinstance(contexts[0]["exception"], ValueError)


@pytest.mark.asyncio
async def test_scheduler_reports_callback_exceptions_without_stopping():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		scheduler.call_soon(_raise_callback)
		survivor = scheduler.create_task(asyncio.sleep(0.02))
		await survivor
		assert contexts
		assert contexts[0]["message"] == "Unhandled exception in later() callback"


@pytest.mark.asyncio
async def test_scheduler_callbacks_run_untracked():
	async with Scheduler("test") as scheduler:
		task = scheduler.call_soon(lambda: None)
		await task


@pytest.mark.asyncio
async def test_render_session_scheduler_closes_without_lingering_tasks():
	session = RenderSession("test-id", RouteTree([Route("a", simple_component)]))
	await session.scheduler.start()
	started = asyncio.Event()

	async def work():
		started.set()
		await asyncio.sleep(10)

	with ps.PulseContext.update(render=session):
		task = session.create_task(work())
	await wait_for(lambda: started.is_set(), timeout=0.2)
	await session.close()
	assert task.cancelled()


async def _raise(exception: Exception) -> None:
	raise exception


def _raise_callback() -> None:
	raise ValueError("callback")
