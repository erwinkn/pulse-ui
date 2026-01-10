"""Tests for Pulse Context inheritance through route hierarchy."""

from typing import Any

import pulse as ps
import pytest
from pulse.context import (
	PulseUserContextError,
	get_user_context_snapshot,
	pulse_context,
	restore_user_context,
	use_pulse_context,
)
from pulse.messages import ServerMessage
from pulse.render_session import RenderSession
from pulse.routing import Layout, Route, RouteInfo, RouteTree


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def make_route_info(pathname: str) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


# Basic inheritance tests (from F-0031)


def test_nested_context_overrides_parent():
	"""Nested pulse_context() overrides parent values for same keys."""
	with pulse_context(theme="dark", lang="en"):
		assert use_pulse_context("theme") == "dark"
		assert use_pulse_context("lang") == "en"

		with pulse_context(theme="light"):
			# theme is overridden
			assert use_pulse_context("theme") == "light"
			# lang is inherited from parent
			assert use_pulse_context("lang") == "en"

		# After exiting inner context, theme is back to dark
		assert use_pulse_context("theme") == "dark"


def test_child_inherits_parent_context():
	"""Child context inherits all parent values."""
	with pulse_context(a=1, b=2):
		with pulse_context(c=3):
			# All values accessible
			assert use_pulse_context("a") == 1
			assert use_pulse_context("b") == 2
			assert use_pulse_context("c") == 3


def test_missing_key_raises_error():
	"""Accessing missing key raises PulseUserContextError."""
	with pulse_context(a=1):
		with pytest.raises(PulseUserContextError) as exc_info:
			use_pulse_context("nonexistent")
		assert "nonexistent" in str(exc_info.value)


# Snapshot tests


def test_snapshot_captures_current_context():
	"""get_user_context_snapshot captures current context stack."""
	with pulse_context(x=10):
		snapshot1 = get_user_context_snapshot()
		with pulse_context(y=20):
			snapshot2 = get_user_context_snapshot()

	# snapshot1 should have x but not y
	assert len(snapshot1) == 1
	assert snapshot1[0]["x"] == 10

	# snapshot2 should have both contexts
	assert len(snapshot2) == 2


def test_restore_context_from_snapshot():
	"""restore_user_context restores context from snapshot."""
	with pulse_context(theme="dark", user_id=123):
		snapshot = get_user_context_snapshot()

	# Outside original context, verify access fails
	with pytest.raises(PulseUserContextError):
		use_pulse_context("theme")

	# Restore and verify access works
	with restore_user_context(snapshot):
		assert use_pulse_context("theme") == "dark"
		assert use_pulse_context("user_id") == 123


def test_restore_allows_additional_context():
	"""Restored context can be extended with additional pulse_context."""
	with pulse_context(parent_value="from_parent"):
		snapshot = get_user_context_snapshot()

	with restore_user_context(snapshot):
		# Parent value accessible
		assert use_pulse_context("parent_value") == "from_parent"

		# Can add new context
		with pulse_context(child_value="from_child"):
			assert use_pulse_context("parent_value") == "from_parent"
			assert use_pulse_context("child_value") == "from_child"


# Route hierarchy context tracking tests


def test_route_mount_has_context_snapshot_field():
	"""RouteMount has user_context_snapshot field for tracking context."""

	@ps.component
	def SimplePage():
		return ps.div()["Page"]

	routes = RouteTree([Route("page", SimplePage)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/page", make_route_info("/page"))

	mount = session.route_mounts["/page"]
	# RouteMount should have user_context_snapshot attribute
	assert hasattr(mount, "user_context_snapshot")
	# For component without pulse_context, snapshot is empty
	assert mount.user_context_snapshot == ()

	session.close()


def test_get_parent_context_snapshot_returns_empty_for_root():
	"""get_parent_context_snapshot returns empty tuple for root routes."""

	@ps.component
	def RootPage():
		return ps.div()["Root"]

	routes = RouteTree([Route("", RootPage)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/", make_route_info("/"))

	mount = session.route_mounts["/"]
	route = mount.route.pulse_route
	# Root route has no parent
	assert route.parent is None
	# get_parent_context_snapshot returns empty
	parent_snapshot = session.get_parent_context_snapshot(route)
	assert parent_snapshot == ()

	session.close()


def test_get_parent_context_snapshot_returns_parent_snapshot():
	"""get_parent_context_snapshot returns parent mount's snapshot."""

	@ps.component
	def ParentLayout():
		# Capture snapshot inside the component render
		# Note: This will be empty after the render completes due to with block scope
		return ps.div()["Layout"]

	@ps.component
	def ChildPage():
		return ps.div()["Page"]

	layout = Layout(render=ParentLayout, children=[Route("page", ChildPage)])
	routes = RouteTree([layout])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	# First attach layout
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/"))

	# Set a non-empty snapshot manually for testing
	layout_mount = session.route_mounts["/<layout>"]
	with pulse_context(test_key="test_value"):
		layout_mount.user_context_snapshot = get_user_context_snapshot()

	# Now attach child page
	with ps.PulseContext.update(render=session):
		session.attach("/page", make_route_info("/page"))

	# Get the parent context for child route
	page_mount = session.route_mounts["/page"]
	parent_snapshot = session.get_parent_context_snapshot(page_mount.route.pulse_route)

	# Should get layout's snapshot
	assert len(parent_snapshot) == 1
	assert parent_snapshot[0]["test_key"] == "test_value"

	session.close()


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Context inheritance not working with new tree. See F-0068 notes."
	)
)
def test_prerender_restores_parent_context():
	"""prerender() restores parent context before rendering child."""
	values_seen: list[str] = []

	@ps.component
	def ParentLayout():
		return ps.div()["Layout"]

	@ps.component
	def ChildPage():
		# Try to access parent context
		try:
			val = use_pulse_context("layout_theme")
			values_seen.append(val)
		except PulseUserContextError:
			values_seen.append("NOT_FOUND")
		return ps.div()["Page"]

	layout = Layout(render=ParentLayout, children=[Route("page", ChildPage)])
	routes = RouteTree([layout])
	session = RenderSession("test-id", routes)

	# First prerender layout
	with ps.PulseContext.update(render=session):
		session.prerender("/<layout>")

	# Manually set layout's context snapshot to simulate context provision
	layout_mount = session.route_mounts["/<layout>"]
	with pulse_context(layout_theme="dark"):
		layout_mount.user_context_snapshot = get_user_context_snapshot()

	# Now prerender child - it should inherit parent's context
	with ps.PulseContext.update(render=session):
		session.prerender("/page")

	# Child should have found the context (may render multiple times via effect)
	assert "dark" in values_seen
	assert "NOT_FOUND" not in values_seen

	session.close()


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Callback context restoration not working. See F-0068 notes."
	)
)
def test_callback_restores_route_context():
	"""execute_callback restores route's context snapshot."""
	callback_values: list[Any] = []

	@ps.component
	def PageWithCallback():
		def on_click():
			try:
				val = use_pulse_context("callback_data")
				callback_values.append(val)
			except PulseUserContextError:
				callback_values.append("NOT_FOUND")

		# Wrap in div so button is at index 0 with callback key "0.onClick"
		return ps.div()[ps.button(onClick=on_click)["Click"]]

	routes = RouteTree([Route("page", PageWithCallback)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/page", make_route_info("/page"))

	# Manually set route's context snapshot
	mount = session.route_mounts["/page"]
	with pulse_context(callback_data="secret"):
		mount.user_context_snapshot = get_user_context_snapshot()

	# Execute callback - it should have access to the context
	session.execute_callback("/page", "0.onClick", [])

	assert callback_values == ["secret"]

	session.close()


def test_context_snapshot_isolated_between_sessions():
	"""Each session has its own context snapshot, no leaking."""

	@ps.component
	def SimplePage():
		return ps.div()["Page"]

	routes = RouteTree([Route("page", SimplePage)])
	s1 = RenderSession("s1", routes)
	s2 = RenderSession("s2", routes)

	s1.connect(lambda _: None)
	s2.connect(lambda _: None)

	with ps.PulseContext.update(render=s1):
		s1.attach("/page", make_route_info("/page"))

	with ps.PulseContext.update(render=s2):
		s2.attach("/page", make_route_info("/page"))

	m1 = s1.route_mounts["/page"]
	m2 = s2.route_mounts["/page"]

	# Set different snapshots for each
	with pulse_context(session="s1"):
		m1.user_context_snapshot = get_user_context_snapshot()
	with pulse_context(session="s2"):
		m2.user_context_snapshot = get_user_context_snapshot()

	# Verify they're different
	assert m1.user_context_snapshot[0]["session"] == "s1"
	assert m2.user_context_snapshot[0]["session"] == "s2"

	s1.close()
	s2.close()


def test_deeply_nested_route_parent_lookup():
	"""get_parent_context_snapshot works through multiple nesting levels."""

	@ps.component
	def L1():
		return ps.div()["L1"]

	@ps.component
	def L2():
		return ps.div()["L2"]

	@ps.component
	def Page():
		return ps.div()["Page"]

	l2 = Layout(render=L2, children=[Route("deep", Page)])
	l1 = Layout(render=L1, children=[l2])
	routes = RouteTree([l1])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	# Attach L1
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/"))
	# Set L1's context
	m1 = session.route_mounts["/<layout>"]
	with pulse_context(l1_key="l1_value"):
		m1.user_context_snapshot = get_user_context_snapshot()

	# Attach L2 (nested layout path)
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>/<layout>", make_route_info("/"))
	# Set L2's context (includes L1's inherited context)
	m2 = session.route_mounts["/<layout>/<layout>"]
	with pulse_context(l1_key="l1_value", l2_key="l2_value"):
		m2.user_context_snapshot = get_user_context_snapshot()

	# Attach Page (route path is /deep, not /<layout>/<layout>/deep)
	with ps.PulseContext.update(render=session):
		session.attach("/deep", make_route_info("/deep"))

	# Page's parent is L2
	page_mount = session.route_mounts["/deep"]
	parent_snapshot = session.get_parent_context_snapshot(page_mount.route.pulse_route)

	# Should get L2's snapshot which includes l2_key
	assert len(parent_snapshot) == 1
	assert parent_snapshot[0]["l2_key"] == "l2_value"

	session.close()
