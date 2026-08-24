import asyncio
import time
from collections.abc import Callable

from pulse.scheduling import CLOCK_RESOLUTION, clamp_delay


def slow_delay(seconds: float = 0.01) -> float:
	"""Return a sleep long enough to be observable given the platform clock resolution."""
	return max(seconds, 2 * CLOCK_RESOLUTION)


async def wait_for(
	condition: Callable[[], bool], *, timeout: float = 1.0, poll_interval: float = 0.005
) -> bool:
	"""Poll until condition() is truthy or timeout. Returns True if condition met."""
	deadline = time.perf_counter() + timeout
	while time.perf_counter() < deadline:
		if condition():
			return True
		await asyncio.sleep(clamp_delay(poll_interval))
	return False
