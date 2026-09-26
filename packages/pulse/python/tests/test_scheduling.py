import asyncio
import threading
import warnings

import pulse as ps
import pytest
from pulse.reactive import Scope, Signal
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteTree
from pulse.tasks import Task, TaskOutcome, TaskScope
from pulse.test_helpers import wait_for


@ps.component
def simple_component():
	return ps.div()


@pytest.mark.asyncio
async def test_scheduler_spawns_and_tracks_tasks():
	async with TaskScope("test") as scheduler:
		started = asyncio.Event()

		async def work():
			started.set()

		task = scheduler.spawn(work(), name="test.task")
		assert isinstance(task, Task)
		assert await task.wait() is TaskOutcome.COMPLETED
		assert started.is_set()
		assert task.done()
		assert not task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_later_and_repeat():
	async with TaskScope("test") as scheduler:
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
		assert repeat.cancelled()


@pytest.mark.asyncio
async def test_scheduler_repeat_waits_before_first_run():
	async with TaskScope("test") as scheduler:
		fired = asyncio.Event()

		def callback():
			fired.set()

		task = scheduler.repeat(10, callback)
		await asyncio.sleep(0.02)
		assert not fired.is_set()
		task.cancel()


@pytest.mark.asyncio
async def test_scheduler_every_runs_before_first_interval():
	async with TaskScope("test") as scheduler:
		started = asyncio.Event()
		loop = asyncio.get_running_loop()
		start = loop.time()

		def callback():
			started.set()

		task = scheduler.every(10, callback)
		await started.wait()
		assert loop.time() - start < 10
		task.cancel()


@pytest.mark.asyncio
async def test_scheduler_repeat_kwargs_reach_callback():
	async def run(scope: TaskScope) -> None:
		seen: list[int] = []
		done = asyncio.Event()

		def callback(value: int, *, flag: bool) -> None:
			seen.append(value)
			assert flag
			done.set()

		task = scope.every(0.01, callback, 7, flag=True)
		await done.wait()
		task.cancel()
		assert seen[0] == 7

	async with TaskScope("test") as scheduler:
		await run(scheduler)


@pytest.mark.asyncio
async def test_scheduler_runs_async_callbacks():
	async with TaskScope("test") as scheduler:
		fired = asyncio.Event()

		async def callback():
			await asyncio.sleep(0)
			fired.set()

		task = scheduler.later(0.01, callback)
		assert await task.wait() is TaskOutcome.COMPLETED
		assert fired.is_set()


@pytest.mark.asyncio
async def test_scheduler_rejects_scheduling_from_another_thread():
	async with TaskScope("test") as scheduler:
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
async def test_scheduler_rejects_before_start_and_after_close():
	scheduler = TaskScope("test")
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
	scheduler = TaskScope("test")
	await scheduler.start()
	with pytest.raises(RuntimeError, match="already running"):
		await scheduler.start()
	await scheduler.close()
	await scheduler.close()
	assert not scheduler.running


@pytest.mark.asyncio
async def test_scheduler_cancel_before_first_tick():
	async with TaskScope("test") as scheduler:
		fired = False

		def callback():
			nonlocal fired
			fired = True

		task = scheduler.later(1, callback)
		await asyncio.sleep(0.001)
		task.cancel()
		await asyncio.sleep(0.05)
		assert not fired
		assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_cancelled_task_has_no_unawaited_warning():
	async with TaskScope("test") as scheduler:
		started = asyncio.Event()

		async def work():
			started.set()
			await asyncio.sleep(1)

		with warnings.catch_warnings(record=True) as caught:
			warnings.simplefilter("always")
			task = scheduler.spawn(work())
			await started.wait()
			task.cancel()
			await wait_for(task.cancelled, timeout=0.2)
		assert await task.wait() is TaskOutcome.CANCELLED
		assert task.cancelled()
		assert not any("never awaited" in str(w.message) for w in caught)


@pytest.mark.asyncio
async def test_scheduler_close_drains_cancelled_tasks():
	scheduler = TaskScope("test")
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
	assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_isolates_task_exceptions():
	async with TaskScope("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		task = scheduler.spawn(_raise(ValueError("task")), name="task")
		survivor = scheduler.spawn(asyncio.sleep(0.02))
		assert await task.wait() is TaskOutcome.COMPLETED
		await survivor.wait()
		await asyncio.sleep(0)
		assert contexts
		assert contexts[0]["message"] == "Unhandled exception in task task"
		assert isinstance(contexts[0]["exception"], ValueError)


@pytest.mark.asyncio
async def test_scheduler_reports_callback_exceptions_without_stopping():
	async with TaskScope("test") as scheduler:
		loop = asyncio.get_running_loop()
		contexts: list[dict[str, object]] = []
		loop.set_exception_handler(lambda _, context: contexts.append(context))
		task = scheduler.later(0, _raise_callback)
		survivor = scheduler.spawn(asyncio.sleep(0.02))
		await task.wait()
		await survivor.wait()
		assert contexts
		assert contexts[0]["message"] == (
			"Unhandled exception in task later:_raise_callback"
		)


@pytest.mark.asyncio
async def test_scheduler_repeat_survives_callback_exceptions():
	async with TaskScope("test") as scheduler:
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
	async with TaskScope("test") as scheduler:
		signal = Signal(1)

		def sync_reader():
			_ = signal()

		async def async_reader():
			_ = signal()

		with Scope() as sync_scope:
			await scheduler.later(0, sync_reader).wait()
		assert sync_scope.deps == {}

		with Scope() as async_scope:
			await scheduler.later(0, async_reader).wait()
		assert async_scope.deps == {}


@pytest.mark.asyncio
async def test_render_session_scheduler_closes_without_lingering_tasks():
	session = RenderSession("test-id", RouteTree([Route("a", simple_component)]))
	await session.task_scope.start()
	started = asyncio.Event()

	async def work():
		started.set()
		await asyncio.sleep(10)

	with ps.PulseContext.update(render=session):
		task = session.spawn(work())
	await wait_for(lambda: started.is_set(), timeout=0.2)
	await session.close()
	assert task.cancelled()
	assert task.done()


async def _raise(exception: Exception) -> None:
	raise exception


def _raise_callback() -> None:
	raise ValueError("callback")
