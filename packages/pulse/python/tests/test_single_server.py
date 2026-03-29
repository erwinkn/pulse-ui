"""
Unit tests for single-server deployment mode.
"""

import pytest
from pulse import App, Route, component


@component
def DummyPage():
	return None


def test_api_prefix_in_single_server_mode():
	"""Test that single-server mode defaults to /_pulse prefix."""
	app = App(routes=[], mode="single-server")
	assert app.api_prefix == "/_pulse"


def test_api_prefix_in_subdomains_mode():
	"""Test that subdomains mode defaults to /_pulse prefix."""
	app = App(routes=[], mode="subdomains")
	assert app.api_prefix == "/_pulse"


def test_framework_namespace_is_reserved():
	"""User routes cannot overlap with framework-owned endpoints."""
	with pytest.raises(ValueError, match=r"Routes under '/_pulse/\*' are reserved"):
		App(routes=[Route("/_pulse/debug", render=DummyPage)])


def test_deployment_mode_defaults_to_single_server():
	"""Test that deployment defaults to subdomains."""
	app = App(routes=[])
	assert app.mode == "single-server"
	assert app.api_prefix == "/_pulse"
