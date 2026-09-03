import asyncio
import threading
import warnings

import pulse as ps
import pytest
from anyio import TaskHandle, to_thread
from pulse.reactive import Scope, Signal
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.scheduling import Scheduler, is_pending
from pulse.test_helpers import wait_for


@ps.component
def simple_component():
	return ps.div()


@pytest.mark.asyncio
async def test_scheduler_spawns_and_tracks_tasks():
	async with Scheduler("test") as scheduler:
		started = asyncio.Event()

		async def work():
			started.set()

		task = scheduler.spawn(work(), name="test.task")
		assert isinstance(task, TaskHandle)
		assert await task is None
		assert started.is_set()
		assert task.status is TaskHandle.Status.FINISHED


@pytest.mark.asyncio
async def test_scheduler_later_and_repeat():
	async with Scheduler("test") as scheduler:
		events: list[str] = []
		repeated = asyncio.Event()

		def later_callback():
			events.append("later")

		def repeat_callback():
			events.append("repeat")
			repeated.set()

		scheduler.later(0.01, later_callback)
		repeat = scheduler.repeat(0.01, repeat_callback)
		await wait_for(lambda: repeated.is_set(), timeout=0.2)
		assert await wait_for(lambda: "later" in events, timeout=0.2)
		repeat.cancel()
		await asyncio.sleep(0)
		assert "later" in events
		assert "repeat" in events
		assert repeat.status is TaskHandle.Status.CANCELLED


@pytest.mark.asyncio
async def test_scheduler_repeat_immediate_runs_before_first_interval():
	async with Scheduler("test") as scheduler:
		started = asyncio.Event()
		loop = asyncio.get_running_loop()
		start = loop.time()

		def callback():
			started.set()

		task = scheduler.repeat(10, callback, immediate=True)
		await started.wait()
		assert loop.time() - start < 10
		task.cancel()


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
async def test_scheduler_rejects_scheduling_from_another_thread():
	async with Scheduler("test") as scheduler:
		errors: list[BaseException] = []

		def schedule():
			coroutine = asyncio.sleep(0)
			try:
				scheduler.spawn(coroutine)
			except BaseException as exc:
				errors.append(exc)
				coroutine.close()

		thread = threading.Thread(target=schedule)
		thread.start()
		await asyncio.to_thread(thread.join)
		assert len(errors) == 1
		assert str(errors[0]) == "cannot schedule on test from outside its event loop"


@pytest.mark.asyncio
async def test_scheduler_post_runs_on_owning_loop_from_threads():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		events: list[asyncio.AbstractEventLoop] = []
		finished = asyncio.Event()

		def callback():
			events.append(asyncio.get_running_loop())
			finished.set()

		thread = threading.Thread(target=lambda: scheduler.post(callback))
		thread.start()
		await to_thread.run_sync(thread.join)
		await finished.wait()
		assert events == [loop]

		finished.clear()
		await to_thread.run_sync(lambda: scheduler.post(callback))
		await finished.wait()
		assert events == [loop, loop]

		finished.clear()
		scheduler.post(callback)
		assert events == [loop, loop]
		await finished.wait()
		assert events == [loop, loop, loop]


@pytest.mark.asyncio
async def test_scheduler_post_before_start_raises_and_after_close_is_noop():
	scheduler = Scheduler("test")
	with pytest.raises(RuntimeError, match="it has never run"):
		scheduler.post(lambda: None)

	await scheduler.start()
	await scheduler.close()
	fired = False

	def callback():
		nonlocal fired
		fired = True

	scheduler.post(callback)
	await asyncio.sleep(0)
	assert not fired


@pytest.mark.asyncio
async def test_scheduler_post_callback_failures_are_reported_and_isolated():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		finished = asyncio.Event()

		def callback():
			raise ValueError("post")

		def survivor():
			finished.set()

		thread = threading.Thread(target=lambda: scheduler.post(callback))
		thread.start()
		await to_thread.run_sync(thread.join)
		scheduler.post(survivor)
		await finished.wait()
		assert await wait_for(lambda: len(contexts) == 1, timeout=0.2)
		assert contexts[0]["message"] == (
			f"Unhandled exception in post({callback.__qualname__})"
		)
		assert isinstance(contexts[0]["exception"], ValueError)


@pytest.mark.asyncio
async def test_scheduler_post_callbacks_run_untracked():
	async with Scheduler("test") as scheduler:
		signal = Signal(1)
		finished = asyncio.Event()

		def callback():
			signal()
			finished.set()

		with Scope() as scope:
			scheduler.post(callback)
			await finished.wait()
		assert scope.deps == {}


@pytest.mark.asyncio
async def test_scheduler_rejects_before_start_and_after_close():
	scheduler = Scheduler("test")
	coroutine = asyncio.sleep(0)
	with pytest.raises(RuntimeError, match="it is not running"):
		scheduler.spawn(coroutine)
	coroutine.close()
	await scheduler.start()
	await scheduler.close()
	coroutine = asyncio.sleep(0)
	with pytest.raises(RuntimeError, match="it is not running"):
		scheduler.spawn(coroutine)
	coroutine.close()


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

		task = scheduler.later(1, callback)
		await asyncio.sleep(0.001)
		task.cancel()
		await asyncio.sleep(0.05)
		assert not fired
		assert task.status is TaskHandle.Status.CANCELLED


@pytest.mark.asyncio
async def test_scheduler_cancelled_task_has_no_unawaited_warning():
	async with Scheduler("test") as scheduler:
		started = asyncio.Event()

		async def work():
			started.set()
			await asyncio.sleep(1)

		with warnings.catch_warnings(record=True) as caught:
			warnings.simplefilter("always")
			task = scheduler.spawn(work())
			await started.wait()
			task.cancel()
			await wait_for(
				lambda: task.status is TaskHandle.Status.CANCELLED, timeout=0.2
			)
		assert task.status is TaskHandle.Status.CANCELLED
		assert not any("never awaited" in str(w.message) for w in caught)


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

	task = scheduler.spawn(work())
	await asyncio.sleep(0)
	await scheduler.close()
	assert cancelled.is_set()
	assert task.status is TaskHandle.Status.CANCELLED


@pytest.mark.asyncio
async def test_scheduler_isolates_task_exceptions():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		task = scheduler.spawn(_raise(ValueError("task")), name="task")
		survivor = scheduler.spawn(asyncio.sleep(0.02))
		await task
		await survivor
		await asyncio.sleep(0)
		assert contexts
		assert contexts[0]["message"] == "Unhandled exception in task task"
		assert isinstance(contexts[0]["exception"], ValueError)


@pytest.mark.asyncio
async def test_scheduler_reports_callback_exceptions_without_stopping():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		task = scheduler.later(0, _raise_callback)
		survivor = scheduler.spawn(asyncio.sleep(0.02))
		await task
		await survivor
		assert contexts
		assert contexts[0]["message"] == (
			"Unhandled exception in task later:_raise_callback"
		)


@pytest.mark.asyncio
async def test_scheduler_repeat_survives_callback_exceptions():
	async with Scheduler("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		calls = 0
		finished = asyncio.Event()

		def callback():
			nonlocal calls
			calls += 1
			if calls == 1:
				raise ValueError("repeat")
			finished.set()

		task = scheduler.repeat(0.01, callback)
		await finished.wait()
		task.cancel()
		assert calls >= 2
		assert contexts
		assert contexts[0]["message"] == (
			"Unhandled exception in repeat("
			"test_scheduler_repeat_survives_callback_exceptions.<locals>.callback)"
		)


@pytest.mark.asyncio
async def test_scheduler_callbacks_run_untracked():
	async with Scheduler("test") as scheduler:
		signal = Signal(1)
		with Scope() as scope:
			task = scheduler.later(0, signal)
			await task
		assert scope.deps == {}


@pytest.mark.asyncio
async def test_render_session_scheduler_closes_without_lingering_tasks():
	session = RenderSession("test-id", RouteTree([Route("a", simple_component)]))
	await session.scheduler.start()
	started = asyncio.Event()

	async def work():
		started.set()
		await asyncio.sleep(10)

	with ps.PulseContext.update(render=session):
		task = session.spawn(work())
	await wait_for(lambda: started.is_set(), timeout=0.2)
	await session.close()
	assert task.status is TaskHandle.Status.CANCELLED
	assert not is_pending(task)


async def _raise(exception: Exception) -> None:
	raise exception


def _raise_callback() -> None:
	raise ValueError("callback")
