import asyncio
import threading

import pytest
from pulse.loop import LoopRef, post


@pytest.mark.asyncio
async def test_run_inline_on_loop_passes_loop():
	loop = asyncio.get_running_loop()
	ref = LoopRef(loop=loop)

	assert ref.run(lambda received: received) is loop


@pytest.mark.asyncio
async def test_run_unbound_adopts_running_loop_without_binding():
	loop = asyncio.get_running_loop()
	ref = LoopRef()

	assert ref.run(lambda received: received) is loop
	assert ref.loop is None


def test_run_unbound_without_loop_on_worker_thread_raises():
	ref = LoopRef("tasks")
	errors: list[BaseException] = []

	def invoke() -> None:
		try:
			ref.run(lambda loop: loop)
		except BaseException as exc:
			errors.append(exc)

	thread = threading.Thread(target=invoke)
	thread.start()
	thread.join()

	assert len(errors) == 1
	assert str(errors[0]) == "cannot schedule: tasks has no bound event loop"


@pytest.mark.asyncio
async def test_run_foreign_running_loop_raises():
	ref = LoopRef("tasks", loop=asyncio.get_running_loop())

	def run() -> None:
		async def invoke() -> None:
			ref.run(lambda loop: loop)

		asyncio.run(invoke())

	with pytest.raises(RuntimeError, match="different event loop"):
		await asyncio.to_thread(run)


@pytest.mark.asyncio
async def test_run_marshals_from_thread_and_returns_value():
	ref = LoopRef(loop=asyncio.get_running_loop())
	result: list[int] = []

	thread = threading.Thread(target=lambda: result.append(ref.run(lambda loop: 42)))
	thread.start()
	await asyncio.to_thread(thread.join)

	assert result == [42]


@pytest.mark.asyncio
async def test_run_propagates_exception_to_calling_thread():
	ref = LoopRef(loop=asyncio.get_running_loop())
	errors: list[BaseException] = []

	def invoke() -> None:
		try:
			ref.run(lambda loop: 1 / 0)
		except BaseException as exc:
			errors.append(exc)

	thread = threading.Thread(target=invoke)
	thread.start()
	await asyncio.to_thread(thread.join)

	assert len(errors) == 1
	assert isinstance(errors[0], ZeroDivisionError)


@pytest.mark.asyncio
async def test_post_runs_inline_on_loop():
	loop = asyncio.get_running_loop()
	called: list[asyncio.AbstractEventLoop] = []

	post(loop, lambda: called.append(asyncio.get_running_loop()))

	assert called == [loop]


@pytest.mark.asyncio
async def test_post_marshals_from_thread():
	loop = asyncio.get_running_loop()
	done = asyncio.Event()

	thread = threading.Thread(target=lambda: post(loop, done.set))
	thread.start()
	await asyncio.to_thread(thread.join)

	await asyncio.wait_for(done.wait(), timeout=0.2)


def test_post_closed_loop_is_noop():
	loop = asyncio.new_event_loop()
	loop.close()

	post(loop, lambda: pytest.fail("closed loop callback ran"))
