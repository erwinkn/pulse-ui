"""
Unit tests for single-server deployment mode.
"""

from pulse import App


def test_api_prefix_in_single_server_mode():
	"""Test that single-server mode defaults to /api/pulse prefix."""
	app = App(routes=[], deployment="single-server")
	assert app.api_prefix == "/api/pulse"


def test_api_prefix_in_subdomains_mode():
	"""Test that subdomains mode has no prefix."""
	app = App(routes=[], deployment="subdomains")
	assert app.api_prefix == ""


def test_api_prefix_in_same_host_mode():
	"""Test that same_host mode has no prefix."""
	app = App(routes=[], deployment="same_host")
	assert app.api_prefix == ""


def test_custom_api_prefix():
	"""Test that custom api_prefix overrides default."""
	app = App(routes=[], deployment="single-server", api_prefix="/custom/api")
	assert app.api_prefix == "/custom/api"


def test_custom_api_prefix_with_subdomains():
	"""Test that custom api_prefix works with subdomains mode."""
	app = App(routes=[], deployment="subdomains", api_prefix="/api/v1")
	assert app.api_prefix == "/api/v1"


def test_deployment_mode_dev_defaults_to_no_prefix():
	"""Test that dev mode deployment defaults to no prefix."""
	app = App(routes=[], mode="dev")
	assert app.deployment == "dev"
	assert app.api_prefix == ""
