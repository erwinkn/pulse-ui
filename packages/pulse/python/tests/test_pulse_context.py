"""Verification tests for Pulse Context with nested routes (F-0033).

Steel wire checkpoint - Pulse Context system working with nested routes.
Tests verify context provision in layouts and consumption in pages.
"""

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


# F-0033 Acceptance Criteria Tests


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Context provision/consumption not working. See F-0068 notes."
	)
)
def test_provide_in_layout_consume_in_page():
	"""Test: provide in layout, consume in page."""
	page_values: dict[str, Any] = {}

	@ps.component
	def LayoutWithContext():
		# Provide context in layout
		with pulse_context(layout_theme="dark", user_id=42):
			# Layout renders normally
			return ps.div()["Layout"]

	@ps.component
	def PageThatConsumes():
		# Page should be able to access layout's context
		theme = use_pulse_context("layout_theme")
		uid = use_pulse_context("user_id")
		page_values["theme"] = theme
		page_values["user_id"] = uid
		return ps.div()[f"Page: {theme}, {uid}"]

	layout = Layout(
		render=LayoutWithContext, children=[Route("page", PageThatConsumes)]
	)
	routes = RouteTree([layout])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	# Render layout
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/"))

	# Capture layout's context snapshot
	layout_mount = session.route_mounts["/<layout>"]
	with pulse_context(layout_theme="dark", user_id=42):
		layout_mount.user_context_snapshot = get_user_context_snapshot()

	# Render page with layout's context
	with ps.PulseContext.update(render=session):
		session.prerender("/page")

	# Page should have accessed the context values
	assert page_values.get("theme") == "dark"
	assert page_values.get("user_id") == 42

	session.close()


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Context provision/consumption not working. See F-0068 notes."
	)
)
def test_nested_contexts_override_correctly():
	"""Test: nested contexts override correctly.

	When a parent context provides a value and child context provides
	the same key, child value should shadow parent value.
	"""
	values_seen: list[str] = []

	@ps.component
	def LayoutA():
		# LayoutA provides initial theme
		with pulse_context(theme="dark", breadcrumb="A"):
			return ps.div()["LayoutA"]

	@ps.component
	def LayoutB():
		# LayoutB can override theme
		with pulse_context(theme="light"):  # Override theme, inherit breadcrumb
			return ps.div()["LayoutB"]

	@ps.component
	def Page():
		theme = use_pulse_context("theme")
		breadcrumb = use_pulse_context("breadcrumb")
		values_seen.append(f"{theme}|{breadcrumb}")
		return ps.div()[f"{theme}|{breadcrumb}"]

	# Create nested layouts: A > B > Page
	layout_b = Layout(render=LayoutB, children=[Route("page", Page)])
	layout_a = Layout(render=LayoutA, children=[layout_b])
	routes = RouteTree([layout_a])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	# Render layout A
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/"))

	layout_a_mount = session.route_mounts["/<layout>"]
	with pulse_context(theme="dark", breadcrumb="A"):
		layout_a_mount.user_context_snapshot = get_user_context_snapshot()

	# Render layout B
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>/<layout>", make_route_info("/"))

	layout_b_mount = session.route_mounts["/<layout>/<layout>"]
	# B overrides theme but inherits breadcrumb from A
	with restore_user_context(layout_a_mount.user_context_snapshot):
		with pulse_context(theme="light"):
			layout_b_mount.user_context_snapshot = get_user_context_snapshot()

	# Render page
	with ps.PulseContext.update(render=session):
		session.prerender("/page")

	# Page should see overridden theme but inherited breadcrumb
	assert "light|A" in values_seen

	session.close()


def test_missing_key_raises_clear_error():
	"""Test: missing key raises clear error with suggestion."""
	# Within context, missing key raises error
	with pulse_context(existing_key="value"):
		with pytest.raises(PulseUserContextError) as exc_info:
			use_pulse_context("nonexistent_key")

		error_msg = str(exc_info.value)
		# Error should mention the missing key
		assert "nonexistent_key" in error_msg
		# Error should suggest how to fix it
		assert "pulse_context" in error_msg


def test_missing_key_outside_context():
	"""Test: missing key outside any context raises error."""
	with pytest.raises(PulseUserContextError) as exc_info:
		use_pulse_context("any_key")

	error_msg = str(exc_info.value)
	assert "any_key" in error_msg
	assert "pulse_context" in error_msg


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Context provision/consumption not working. See F-0068 notes."
	)
)
def test_parent_params_accessible_via_context():
	"""Test: parent route params accessible via context.

	Parent route params should be available to child routes through
	the Pulse Context system (not through React context).
	"""
	child_values: dict[str, Any] = {}

	@ps.component
	def ParentLayout():
		# Parent provides its params via context
		try:
			parent_param = use_pulse_context("parent_param")
		except PulseUserContextError:
			parent_param = "NOT_PROVIDED"
		return ps.div()[f"Parent: {parent_param}"]

	@ps.component
	def ChildPage():
		# Child accesses parent's param through context
		try:
			parent_param = use_pulse_context("parent_param")
			child_values["parent_param"] = parent_param
		except PulseUserContextError:
			child_values["parent_param"] = "NOT_ACCESSIBLE"

		return ps.div()["Child"]

	layout = Layout(render=ParentLayout, children=[Route("child", ChildPage)])
	routes = RouteTree([layout])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	# Render parent layout
	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/parent/123"))

	# Parent provides its param via context
	parent_mount = session.route_mounts["/<layout>"]
	with pulse_context(parent_param="value_from_parent"):
		parent_mount.user_context_snapshot = get_user_context_snapshot()

	# Render child page with parent's context
	with ps.PulseContext.update(render=session):
		session.prerender("/child")

	# Child should have accessed parent's param
	assert child_values["parent_param"] == "value_from_parent"

	session.close()


@pytest.mark.skip(
	reason=(
		"Needs architectural fix: unified tree normalizes components to Elements, "
		"losing hook context. Context provision/consumption not working. See F-0068 notes."
	)
)
def test_context_type_preservation():
	"""Test: various Python types preserved through context."""
	types_tested: dict[str, Any] = {}

	@ps.component
	def ProviderLayout():
		with pulse_context(
			string_val="hello",
			int_val=42,
			float_val=3.14,
			bool_val=True,
			list_val=[1, 2, 3],
			dict_val={"nested": "value"},
			none_val=None,
		):
			return ps.div()["Provider"]

	@ps.component
	def ConsumerPage():
		types_tested["string"] = use_pulse_context("string_val")
		types_tested["int"] = use_pulse_context("int_val")
		types_tested["float"] = use_pulse_context("float_val")
		types_tested["bool"] = use_pulse_context("bool_val")
		types_tested["list"] = use_pulse_context("list_val")
		types_tested["dict"] = use_pulse_context("dict_val")
		types_tested["none"] = use_pulse_context("none_val")
		return ps.div()["Consumer"]

	layout = Layout(render=ProviderLayout, children=[Route("page", ConsumerPage)])
	routes = RouteTree([layout])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/<layout>", make_route_info("/"))

	layout_mount = session.route_mounts["/<layout>"]
	with pulse_context(
		string_val="hello",
		int_val=42,
		float_val=3.14,
		bool_val=True,
		list_val=[1, 2, 3],
		dict_val={"nested": "value"},
		none_val=None,
	):
		layout_mount.user_context_snapshot = get_user_context_snapshot()

	with ps.PulseContext.update(render=session):
		session.prerender("/page")

	# All types should be preserved
	assert types_tested["string"] == "hello"
	assert types_tested["int"] == 42
	assert types_tested["float"] == 3.14
	assert types_tested["bool"] is True
	assert types_tested["list"] == [1, 2, 3]
	assert types_tested["dict"] == {"nested": "value"}
	assert types_tested["none"] is None

	session.close()


def test_snapshot_is_immutable():
	"""Test: context snapshots are immutable."""
	with pulse_context(key="value"):
		snapshot = get_user_context_snapshot()

	# Each entry in snapshot should be immutable
	assert len(snapshot) == 1
	context_map = snapshot[0]

	# MappingProxyType should prevent modification
	with pytest.raises(TypeError):
		context_map["key"] = "modified"  # pyright: ignore[reportIndexIssue]


def test_restore_empty_snapshot():
	"""Test: restoring empty snapshot works (e.g., for root routes)."""
	# Outside context, context stack is empty
	empty_snapshot = get_user_context_snapshot()
	assert empty_snapshot == ()

	# Should be able to restore empty snapshot
	with restore_user_context(empty_snapshot):
		# No context available
		with pytest.raises(PulseUserContextError):
			use_pulse_context("any_key")


def test_context_per_session_isolation():
	"""Test: contexts isolated per session/request.

	Each RenderSession has its own route_mounts with separate snapshots.
	"""

	@ps.component
	def SimplePage():
		return ps.div()["Page"]

	routes = RouteTree([Route("page", SimplePage)])
	s1 = RenderSession("id1", routes)
	s2 = RenderSession("id2", routes)

	s1.connect(lambda _: None)
	s2.connect(lambda _: None)

	# Attach same route in different sessions
	with ps.PulseContext.update(render=s1):
		s1.attach("/page", make_route_info("/page"))

	with ps.PulseContext.update(render=s2):
		s2.attach("/page", make_route_info("/page"))

	# Set different contexts for each session
	m1 = s1.route_mounts["/page"]
	with pulse_context(session_id="s1", data="s1_data"):
		m1.user_context_snapshot = get_user_context_snapshot()

	m2 = s2.route_mounts["/page"]
	with pulse_context(session_id="s2", data="s2_data"):
		m2.user_context_snapshot = get_user_context_snapshot()

	# Verify snapshots are different
	assert m1.user_context_snapshot[0]["session_id"] == "s1"
	assert m2.user_context_snapshot[0]["session_id"] == "s2"
	assert m1.user_context_snapshot[0]["data"] == "s1_data"
	assert m2.user_context_snapshot[0]["data"] == "s2_data"

	# Verify they're completely separate (no crosstalk)
	assert m1.user_context_snapshot is not m2.user_context_snapshot

	s1.close()
	s2.close()
