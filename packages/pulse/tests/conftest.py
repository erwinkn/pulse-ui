import pulse as ps
import pytest


@pytest.fixture(autouse=True)
def _pulse_context():
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield
