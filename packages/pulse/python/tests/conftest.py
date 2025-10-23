import pytest
from pulse.app import App
from pulse.context import PulseContext


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	app = App()
	ctx = PulseContext(app=app)
	with ctx:
		yield
