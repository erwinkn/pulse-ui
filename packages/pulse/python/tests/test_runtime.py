import asyncio
import threading

import pytest
from pulse.runtime import LoopBinding
from pulse.test_helpers import wait_for


@pytest.mark.asyncio
async def test_loop_binding_current_is_true_on_bound_loop():
	loop = asyncio.get_running_loop()
	binding = LoopBinding(loop)
	assert binding.current


@pytest.mark.asyncio
async def test_loop_binding_post_runs_on_bound_loop_from_thread():
	loop = asyncio.get_running_loop()
	binding = LoopBinding(loop)
	events: list[asyncio.AbstractEventLoop] = []
	finished = asyncio.Event()

	def callback():
		events.append(asyncio.get_running_loop())
		finished.set()

	thread = threading.Thread(target=lambda: binding.post(callback))
	thread.start()
	await asyncio.to_thread(thread.join)
	await finished.wait()
	assert events == [loop]


@pytest.mark.asyncio
async def test_loop_binding_current_is_false_off_loop_and_post_dispatches():
	loop = asyncio.get_running_loop()
	binding = LoopBinding(loop)
	observed: list[bool] = []
	finished = asyncio.Event()

	def off_loop():
		observed.append(binding.current)
		binding.post(finished.set)

	await asyncio.to_thread(off_loop)
	await finished.wait()
	assert observed == [False]


def test_loop_binding_post_after_close_returns_false():
	loop = asyncio.new_event_loop()
	binding = LoopBinding(loop)
	loop.close()
	assert binding.post(lambda: None) is False


@pytest.mark.asyncio
async def test_loop_binding_post_callback_failures_are_reported_and_isolated():
	loop = asyncio.get_running_loop()
	contexts: list[dict[str, object]] = []
	loop.set_exception_handler(lambda _, context: contexts.append(context))
	binding = LoopBinding(loop)
	finished = asyncio.Event()

	def callback():
		raise ValueError("post")

	def survivor():
		finished.set()

	assert binding.post(callback) is True
	assert binding.post(survivor) is True
	await finished.wait()
	assert await wait_for(lambda: len(contexts) == 1, timeout=0.2)
	assert contexts[0]["message"] == (
		f"Unhandled exception in post({callback.__qualname__})"
	)
	assert isinstance(contexts[0]["exception"], ValueError)
