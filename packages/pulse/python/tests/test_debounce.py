from typing import Any, Callable, cast

import pulse as ps
import pytest
from pulse.test_helpers import wait_for


def test_debounced_marker():
	def handler() -> None:
		pass

	marker = ps.debounced(handler, 120)

	assert isinstance(marker, ps.Debounced)
	assert marker.fn is handler
	assert marker.delay_ms == 120.0


@pytest.mark.parametrize("delay", [-1, float("inf"), float("nan")])
def test_debounced_rejects_invalid_delay(delay: float):
	def handler() -> None:
		pass

	with pytest.raises(ValueError):
		ps.debounced(handler, delay)


def test_debounced_rejects_non_callable():
	with pytest.raises(TypeError):
		ps.debounced(cast(Callable[..., Any], 123), 10)


@pytest.mark.parametrize("delay", [True, "100"])
def test_debounced_rejects_non_number_delay(delay: Any):
	def handler() -> None:
		pass

	with pytest.raises(TypeError):
		ps.debounced(handler, delay)


@pytest.mark.asyncio
async def test_debounced_error_reports_callback_code(caplog: pytest.LogCaptureFixture):
	app = ps.App()

	def explode() -> None:
		raise RuntimeError("debounce-boom")

	fn = ps.debounced(explode, 1)
	with ps.PulseContext(app=app):
		with caplog.at_level("ERROR"):
			fn()
			assert await wait_for(
				lambda: any(
					"code=callback" in rec.getMessage()
					and "debounced" in rec.getMessage()
					for rec in caplog.records
				),
				timeout=0.2,
			)

	await app.close()
