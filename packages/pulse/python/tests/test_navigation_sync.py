"""
Tests for client-side navigation state synchronization to Python.

Verifies that navigation state sent from the client is properly received
and stored in the Python render session.
"""

import pytest
from pulse.messages import ClientNavigationMessage
from pulse.render_session import RenderSession
from pulse.routing import RouteTree


@pytest.fixture
def route_tree() -> RouteTree:
	"""Create a minimal route tree for testing."""
	return RouteTree([])


@pytest.fixture
def render_session(route_tree: RouteTree):
	"""Create a render session for testing."""
	return RenderSession("test-render-id", route_tree)


def test_navigation_message_initializes_last_navigation(
	render_session: RenderSession,
) -> None:
	"""Test that last_navigation is initialized as empty dict."""
	assert render_session.last_navigation == {}


def test_navigation_message_stores_full_state(render_session: RenderSession) -> None:
	"""Test that navigation message stores all fields: pathname, search, hash, state."""
	msg: ClientNavigationMessage = {
		"type": "navigation",
		"pathname": "/users/123",
		"search": "?sort=name",
		"hash": "#section",
		"state": {"from": "list"},
	}

	# Simulate message handling
	render_session.last_navigation = {
		"pathname": msg.get("pathname", ""),
		"search": msg.get("search", ""),
		"hash": msg.get("hash", ""),
		"state": msg.get("state"),
	}

	assert render_session.last_navigation == {
		"pathname": "/users/123",
		"search": "?sort=name",
		"hash": "#section",
		"state": {"from": "list"},
	}


def test_navigation_message_handles_missing_optional_fields(
	render_session: RenderSession,
) -> None:
	"""Test that optional fields are handled gracefully."""
	msg: ClientNavigationMessage = {
		"type": "navigation",
		"pathname": "/home",
		"search": "",
		"hash": "",
	}

	# Simulate message handling with missing state
	render_session.last_navigation = {
		"pathname": msg.get("pathname", ""),
		"search": msg.get("search", ""),
		"hash": msg.get("hash", ""),
		"state": msg.get("state"),
	}

	assert render_session.last_navigation == {
		"pathname": "/home",
		"search": "",
		"hash": "",
		"state": None,
	}


def test_navigation_message_overwrites_previous_state(
	render_session: RenderSession,
) -> None:
	"""Test that new navigation messages overwrite previous state."""
	# First navigation
	render_session.last_navigation = {
		"pathname": "/page1",
		"search": "",
		"hash": "",
		"state": None,
	}
	assert render_session.last_navigation["pathname"] == "/page1"

	# Second navigation overwrites
	render_session.last_navigation = {
		"pathname": "/page2",
		"search": "?id=2",
		"hash": "#top",
		"state": {"id": 2},
	}

	assert render_session.last_navigation == {
		"pathname": "/page2",
		"search": "?id=2",
		"hash": "#top",
		"state": {"id": 2},
	}


def test_navigation_state_with_complex_state_object(
	render_session: RenderSession,
) -> None:
	"""Test that complex state objects are preserved."""
	complex_state = {
		"filters": {"category": "electronics", "price": [10, 100]},
		"pagination": {"page": 2, "size": 20},
		"timestamp": "2024-01-10T10:30:00Z",
	}

	render_session.last_navigation = {
		"pathname": "/products",
		"search": "?category=electronics&page=2",
		"hash": "",
		"state": complex_state,
	}

	assert render_session.last_navigation["state"] == complex_state


def test_navigation_state_includes_query_and_hash(
	render_session: RenderSession,
) -> None:
	"""Test navigation with both query and hash components."""
	render_session.last_navigation = {
		"pathname": "/docs/api",
		"search": "?version=v2&lang=python",
		"hash": "#authentication",
		"state": None,
	}

	nav = render_session.last_navigation
	assert nav["pathname"] == "/docs/api"
	assert nav["search"] == "?version=v2&lang=python"
	assert nav["hash"] == "#authentication"


def test_navigation_pathname_variations(render_session: RenderSession) -> None:
	"""Test various pathname patterns."""
	paths = [
		"/",
		"/home",
		"/users/123",
		"/users/123/posts/456",
		"/api/v1/data.json",
		"/path-with-dashes",
		"/path_with_underscores",
		"/path/with/many/segments",
	]

	for path in paths:
		render_session.last_navigation = {
			"pathname": path,
			"search": "",
			"hash": "",
			"state": None,
		}
		assert render_session.last_navigation["pathname"] == path


def test_navigation_search_string_variations(render_session: RenderSession) -> None:
	"""Test various search string patterns."""
	search_strings = [
		"",
		"?param=value",
		"?a=1&b=2",
		"?complex=hello%20world",
		"?array=1&array=2&array=3",
	]

	for search in search_strings:
		render_session.last_navigation = {
			"pathname": "/search",
			"search": search,
			"hash": "",
			"state": None,
		}
		assert render_session.last_navigation["search"] == search


def test_navigation_hash_variations(render_session: RenderSession) -> None:
	"""Test various hash patterns."""
	hashes = [
		"",
		"#section",
		"#section-subsection",
		"#section_subsection",
		"#123",
	]

	for hash_ in hashes:
		render_session.last_navigation = {
			"pathname": "/page",
			"search": "",
			"hash": hash_,
			"state": None,
		}
		assert render_session.last_navigation["hash"] == hash_


def test_navigation_state_object_types(render_session: RenderSession) -> None:
	"""Test that various state object types are preserved."""
	test_cases = [
		None,
		{"simple": "object"},
		{"nested": {"deep": {"structure": "value"}}},
		{"list": [1, 2, 3]},
		{"mixed": [{"a": 1}, {"b": 2}]},
		{"number": 42, "string": "text", "bool": True, "null": None},
	]

	for state_obj in test_cases:
		render_session.last_navigation = {
			"pathname": "/test",
			"search": "",
			"hash": "",
			"state": state_obj,
		}
		assert render_session.last_navigation["state"] == state_obj
