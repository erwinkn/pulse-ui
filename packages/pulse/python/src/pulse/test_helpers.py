import asyncio
from collections.abc import Callable


async def wait_for(
	condition: Callable[[], bool], *, timeout: float = 1.0, poll_interval: float = 0.005
) -> bool:
	"""Poll until condition() is truthy or timeout. Returns True if condition met."""
	loop = asyncio.get_event_loop()
	deadline = loop.time() + timeout
	while loop.time() < deadline:
		if condition():
			return True
		await asyncio.sleep(poll_interval)
	return False
