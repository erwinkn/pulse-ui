"""
Integration-ish tests for session isolation.

We spin up a minimal route tree with two routes and create two sessions.
Each session mounts both routes and mutates state via callbacks. We assert
that updates from one session do not leak into the other.
"""

import asyncio
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse import javascript
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import ServerMessage
from pulse.reactive import RenderEffect
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.test_helpers import wait_for


@javascript
def get_answer() -> int:
	return 42


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


class CounterState(ps.State):
	count: int = 0

	@ps.effect
	def on_change(self):
		_ = self.count  # track


def Counter(session_name: str, key_prefix: str):
	state = ps.setup(CounterState)

	def inc():
		state.count = state.count + 1

	# Render current count + a callback
	return ps.div(key=f"{key_prefix}:{session_name}")[
		ps.span(id=f"count-{session_name}")[str(state.count)],
		ps.button(onClick=inc)["inc"],
	]


def make_routes() -> RouteTree:
	route_a = Route("a", ps.component(lambda: Counter("A", "route-a")))
	route_b = Route("b", ps.component(lambda: Counter("B", "route-b")))
	return RouteTree([route_a, route_b])


def make_route_info(
	pathname: str, *, path_params: dict[str, str] | None = None
) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": path_params or {},
		"catchall": [],
	}


def transition_view_to_idle(session: RenderSession, path: str) -> None:
	view = session.view_for_path(path)
	view.to_idle()


def attach_view(
	session: RenderSession, path: str, route_info: RouteInfo | None = None
) -> None:
	view = session.view_for_path(path)
	session.attach(view.id, route_info or make_route_info(path))


# TODO: clean this up - this was refactored using GPT-5 and is thus quite hacky
def root_effect(view: Any) -> RenderEffect:
	"""The render effect of the view's root component."""
	runtime = next(iter(view.tree.iter_runtimes()))
	assert runtime.effect is not None
	return runtime.effect


def mount_with_listener(session: RenderSession, path: str):
	# Maintain a session-level set of listened paths and a shared message log
	listened: set[str] | None = getattr(session, "_test_listened_paths", None)
	if listened is None:
		listened = set()
		session._test_listened_paths = listened  # pyright: ignore[reportAttributeAccessIssue]

	log: list[tuple[str, ServerMessage]] | None = getattr(
		session, "_test_message_log", None
	)
	if log is None:
		log = []
		session._test_message_log = log  # pyright: ignore[reportAttributeAccessIssue]

		def on_message(msg: ServerMessage):
			if msg.get("type") == "api_call":
				return
			view_id = msg.get("view")
			if not isinstance(view_id, str):
				return
			view = session.views.get(view_id)
			if view is None:
				return
			# Only record messages for paths we're currently listening to
			if view.route_path in getattr(session, "_test_listened_paths", set()):  # pyright: ignore[reportUnknownArgumentType]
				session._test_message_log.append((view.route_path, msg))  # pyright: ignore[reportAttributeAccessIssue]

		session.connect(on_message)

	# Start listening for this path
	listened.add(path)

	class _PathMessages:
		def __iter__(self):  # type: ignore[override]
			for p, m in getattr(session, "_test_message_log", []):
				if p == path:
					yield m

	# Ensure RenderSession is present in PulseContext when attaching so the
	# captured context for the render effect includes it
	with ps.PulseContext.update(render=session):
		session.prerender(sorted(listened))
		attach_view(session, path)

	def disconnect():
		# Stop listening for this path; messages are still in the shared log
		lst = getattr(session, "_test_listened_paths", set())  # pyright: ignore[reportUnknownArgumentType]
		if isinstance(lst, set):
			lst.discard(path)

	return _PathMessages(), disconnect


def extract_count_from_ctx(session: RenderSession, path: str) -> int:
	# Read latest VDOM by re-rendering from the RenderTree and inspecting it
	view = session.view_for_path(path)
	with ps.PulseContext.update(render=session, route=view.route):
		vdom = view.tree.render()
	vdom_dict = cast(dict[str, Any], cast(object, vdom))
	children = cast(list[Any], (vdom_dict.get("children", []) or []))
	span = cast(dict[str, Any], children[0])
	text_children = cast(list[Any], span.get("children", [0]))
	text = text_children[0]
	return int(text)  # type: ignore[arg-type]


def first_callback_key(session: RenderSession, path: str) -> str:
	return next(iter(session.view_for_path(path).tree.callbacks))


@pytest.mark.asyncio
async def test_pulse_context_update_can_clear_route_source():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	with ps.PulseContext.update(
		render=session,
		route=view.route,
		view=view,
		source_pathname=view.route.pathname,
	):
		with ps.PulseContext.update(
			route=None,
			view=None,
			source_pathname=None,
		):
			ctx = ps.PulseContext.get()
			assert ctx.route is None
			assert ctx.view is None
			assert ctx.source_pathname is None

	session.close()


@pytest.mark.asyncio
async def test_two_sessions_two_routes_are_isolated():
	routes = make_routes()
	s1 = RenderSession("s1", routes)
	s2 = RenderSession("s2", routes)

	# Mount both routes on both sessions and keep listeners active
	msgs_s1_a, disc_s1_a = mount_with_listener(s1, "/a")
	msgs_s1_b, disc_s1_b = mount_with_listener(s1, "/b")
	msgs_s2_a, disc_s2_a = mount_with_listener(s2, "/a")
	msgs_s2_b, disc_s2_b = mount_with_listener(s2, "/b")

	# Initial counts are zero
	assert extract_count_from_ctx(s1, "/a") == 0
	assert extract_count_from_ctx(s1, "/b") == 0
	assert extract_count_from_ctx(s2, "/a") == 0
	assert extract_count_from_ctx(s2, "/b") == 0

	# Click a button in session 1 route a (button is second child, index 1)
	s1.execute_callback(s1.view_for_path("/a").id, "1.onClick", [])
	s1.flush()
	s2.flush()

	# s1:a should update, others should remain unchanged
	assert extract_count_from_ctx(s1, "/a") == 1
	assert extract_count_from_ctx(s1, "/b") == 0
	assert extract_count_from_ctx(s2, "/a") == 0
	assert extract_count_from_ctx(s2, "/b") == 0

	# Ensure s2 did not receive any update messages for either route
	assert len([m for m in msgs_s1_a if m["type"] == "vdom_update"]) == 1
	assert len([m for m in msgs_s1_b if m["type"] == "vdom_update"]) == 0
	assert len([m for m in msgs_s2_a if m["type"] == "vdom_update"]) == 0
	assert len([m for m in msgs_s2_b if m["type"] == "vdom_update"]) == 0

	# Click a button in session 2 route a (button is second child, index 1)
	s2.execute_callback(s2.view_for_path("/a").id, "1.onClick", [])
	s1.flush()
	s2.flush()

	# s2:a should update, others should remain unchanged
	assert extract_count_from_ctx(s1, "/a") == 1
	assert extract_count_from_ctx(s1, "/b") == 0
	assert extract_count_from_ctx(s2, "/a") == 1
	assert extract_count_from_ctx(s2, "/b") == 0

	# Ensure s1 did not receive any update messages for either route
	assert len([m for m in msgs_s1_a if m["type"] == "vdom_update"]) == 1
	assert len([m for m in msgs_s1_b if m["type"] == "vdom_update"]) == 0
	assert len([m for m in msgs_s2_a if m["type"] == "vdom_update"]) == 1
	assert len([m for m in msgs_s2_b if m["type"] == "vdom_update"]) == 0

	# Cleanup listeners and sessions
	disc_s1_a()
	disc_s1_b()
	disc_s2_a()
	disc_s2_b()
	s1.close()
	s2.close()


class GlobalCounterState(ps.State):
	count: int = 0


# Accessor that returns a per-session singleton instance of GlobalCounterState
global_counter = ps.global_state(GlobalCounterState)


def GlobalCounter(tag: str):
	state = global_counter()

	def inc():
		state.count = state.count + 1

	return ps.div(key=f"global-{tag}")[
		ps.span(id=f"gcount-{tag}")[str(state.count)],
		ps.button(onClick=inc)["inc"],
	]


def make_global_routes() -> RouteTree:
	route_a = Route("a", ps.component(lambda: GlobalCounter("A")))
	route_b = Route("b", ps.component(lambda: GlobalCounter("B")))
	return RouteTree([route_a, route_b])


def extract_global_count(session: RenderSession, path: str) -> int:
	view = session.view_for_path(path)
	with ps.PulseContext.update(render=session, route=view.route):
		vdom = view.tree.render()
	vdom_dict = cast(dict[str, Any], cast(object, vdom))
	children = cast(list[Any], (vdom_dict.get("children", []) or []))
	span = cast(dict[str, Any], children[0])
	text_children = cast(list[Any], span.get("children", [0]))
	text = text_children[0]
	return int(text)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_global_state_shared_within_session_and_isolated_across_sessions():
	routes = make_global_routes()
	s1 = RenderSession("s1", routes)
	s2 = RenderSession("s2", routes)

	# Mount both routes on both sessions
	msgs_s1_a, disc_s1_a = mount_with_listener(s1, "/a")
	msgs_s1_b, disc_s1_b = mount_with_listener(s1, "/b")
	msgs_s2_a, disc_s2_a = mount_with_listener(s2, "/a")
	msgs_s2_b, disc_s2_b = mount_with_listener(s2, "/b")

	# Initial counts are zero across both routes/sessions
	assert extract_global_count(s1, "/a") == 0
	assert extract_global_count(s1, "/b") == 0
	assert extract_global_count(s2, "/a") == 0
	assert extract_global_count(s2, "/b") == 0

	# Increment in s1 on route a
	s1.execute_callback(s1.view_for_path("/a").id, "1.onClick", [])
	s1.flush()
	s2.flush()

	# Within s1, both routes reflect the same per-session singleton (value == 1)
	assert extract_global_count(s1, "/a") == 1
	assert extract_global_count(s1, "/b") == 1
	# s2 remains unchanged
	assert extract_global_count(s2, "/a") == 0
	assert extract_global_count(s2, "/b") == 0

	# Route updates in s1 should include both routes
	assert len([m for m in msgs_s1_a if m["type"] == "vdom_update"]) >= 1
	assert len([m for m in msgs_s1_b if m["type"] == "vdom_update"]) >= 1
	# s2 should see no updates
	assert len([m for m in msgs_s2_a if m["type"] == "vdom_update"]) == 0
	assert len([m for m in msgs_s2_b if m["type"] == "vdom_update"]) == 0

	# Increment in s2 on route b
	s2.execute_callback(s2.view_for_path("/b").id, "1.onClick", [])
	s1.flush()
	s2.flush()

	# Within s2, both routes reflect value == 1; s1 unchanged
	assert extract_global_count(s1, "/a") == 1
	assert extract_global_count(s1, "/b") == 1
	assert extract_global_count(s2, "/a") == 1
	assert extract_global_count(s2, "/b") == 1

	# Cleanup listeners and sessions
	disc_s1_a()
	disc_s1_b()
	disc_s2_a()
	disc_s2_b()
	s1.close()
	s2.close()


@pytest.mark.asyncio
async def test_global_state_disposed_on_session_close():
	disposed: list[str] = []

	class Disposable(ps.State):
		count: int = 0

		@override
		def on_dispose(self):
			disposed.append("ok")

	accessor = ps.global_state(Disposable)

	routes = RouteTree(
		[Route("a", ps.component(lambda: ps.div()[ps.span()[str(accessor().count)]]))]
	)
	s = RenderSession("s1", routes)
	_msgs, disc = mount_with_listener(s, "/a")
	# Ensure instance is created by rendering
	assert extract_count_from_ctx(s, "/a") == 0

	# Close session -> should dispose the global singleton instance
	disc()
	s.close()
	assert disposed == ["ok"]


def test_dummy_placeholder_to_keep_line_numbers_stable():
	# Placeholder after revert; keep file stable
	assert True


def test_global_navigate_to_bypasses_pending_view_queue():
	routes = RouteTree(
		[
			Route("a", simple_component),
			Route("a/b", simple_component),
		]
	)
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a", "/a/b"])
		attach_view(session, "/a")
		attach_view(session, "/a/b")

	view = session.view_for_path("/a/b")
	view.start_pending(10)
	assert view.state == "pending"
	assert view.queue == []

	session.send(
		{
			"type": "navigate_to",
			"path": "/a/b",
			"replace": False,
			"hard": False,
		}
	)

	assert len(messages) == 1
	assert messages[0]["type"] == "navigate_to"
	assert view.queue == []

	session.close()


def test_navigate_to_queued_as_global_on_disconnect():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	session.disconnect()
	session.send(
		{
			"type": "navigate_to",
			"path": "/a",
			"replace": False,
			"hard": False,
		}
	)

	assert messages == []

	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	assert len(messages2) == 1
	assert messages2[0]["type"] == "navigate_to"

	session.close()


# =============================================================================
# Reconnection / Rehydration Tests
# =============================================================================


@ps.component
def simple_component():
	return ps.div()["Hello World"]


@pytest.mark.asyncio
async def test_attach_unknown_view_requests_reload():
	"""Test that attaching with an unknown view id requests a reload."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("missing-view", make_route_info("/a"))

	assert session.views == {}
	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

	session.close()


@pytest.mark.asyncio
async def test_async_callback_navigation_after_detach_is_ignored_by_default():
	started = asyncio.Event()
	release = asyncio.Event()
	completed = asyncio.Event()

	@ps.component
	def Page():
		async def on_click():
			started.set()
			await release.wait()
			ps.navigate("/after")
			completed.set()

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach(view.id)
	release.set()
	await asyncio.wait_for(completed.wait(), timeout=0.2)
	await asyncio.sleep(0)

	assert not [msg for msg in messages if msg["type"] == "navigate_to"]
	assert not [msg for msg in messages if msg["type"] == "server_error"]

	session.close()


@pytest.mark.asyncio
async def test_async_callback_force_navigation_after_detach_still_navigates():
	started = asyncio.Event()
	release = asyncio.Event()

	@ps.component
	def Page():
		async def on_click():
			started.set()
			await release.wait()
			ps.navigate("/after", force=True)

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach(view.id)
	release.set()
	await wait_for(lambda: any(msg["type"] == "navigate_to" for msg in messages))

	navigations = [msg for msg in messages if msg["type"] == "navigate_to"]
	assert len(navigations) == 1
	assert navigations[0]["path"] == "/after"

	session.close()


def test_route_bound_navigation_uses_current_path_for_dynamic_routes():
	@ps.component
	def Page():
		return ps.button(onClick=lambda: ps.navigate("/after"))["go"]

	routes = RouteTree([Route("items/:id", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	route_info = make_route_info("/items/123", path_params={"id": "123"})

	with ps.PulseContext.update(render=session):
		session.prerender(["/items/:id"], route_info)
		attach_view(session, "/items/:id", route_info)

	view = session.view_for_path("/items/:id")
	session.execute_callback(
		view.id,
		first_callback_key(session, "/items/:id"),
		[],
	)

	navigations = [msg for msg in messages if msg["type"] == "navigate_to"]
	assert len(navigations) == 1
	assert navigations[0]["path"] == "/after"
	assert navigations[0].get("sourceView") == view.id
	assert navigations[0].get("sourcePathname") == "/items/123"

	session.close()


def test_route_bound_navigation_validates_source_view_identity():
	routes = RouteTree([Route("a", simple_component), Route("b", simple_component)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	route_info = make_route_info("/shared")

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], route_info)
		attach_view(session, "/a", route_info)
		session.prerender(["/b"], route_info)
		attach_view(session, "/b", route_info)

	view = session.view_for_path("/a")
	with ps.PulseContext.update(
		render=session,
		route=view.route,
		view=view,
		source_pathname=view.route.pathname,
	):
		session.detach(view.id)
		ps.navigate("/after")

	# /b is still mounted at the same pathname, but the navigation came from the
	# disposed /a view, so it must be dropped.
	assert session.view_for_path("/b") is not None
	assert not [msg for msg in messages if msg["type"] == "navigate_to"]

	session.close()


@pytest.mark.asyncio
async def test_async_callback_navigation_after_same_url_remount_is_ignored():
	started = asyncio.Event()
	release = asyncio.Event()
	completed = asyncio.Event()

	@ps.component
	def Page():
		async def on_click():
			started.set()
			await release.wait()
			ps.navigate("/after")
			completed.set()

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach(view.id)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	# A fresh view was created for the same path; the old id is gone.
	assert session.view_for_path("/a").id != view.id

	release.set()
	await asyncio.wait_for(completed.wait(), timeout=0.2)
	await asyncio.sleep(0)

	assert not [msg for msg in messages if msg["type"] == "navigate_to"]
	assert not [msg for msg in messages if msg["type"] == "server_error"]

	session.close()


@pytest.mark.asyncio
async def test_async_callback_navigation_after_route_update_is_ignored_by_default():
	started = asyncio.Event()
	release = asyncio.Event()
	completed = asyncio.Event()

	@ps.component
	def Page():
		async def on_click():
			started.set()
			await release.wait()
			ps.navigate("/after")
			completed.set()

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("items/:id", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	first_info = make_route_info("/items/123", path_params={"id": "123"})
	next_info = make_route_info("/items/456", path_params={"id": "456"})

	with ps.PulseContext.update(render=session):
		session.prerender(["/items/:id"], first_info)
		attach_view(session, "/items/:id", first_info)

	view = session.view_for_path("/items/:id")
	session.execute_callback(view.id, first_callback_key(session, "/items/:id"), [])
	await started.wait()
	session.attach(view.id, next_info)
	release.set()
	await asyncio.wait_for(completed.wait(), timeout=0.2)
	await asyncio.sleep(0)

	assert not [msg for msg in messages if msg["type"] == "navigate_to"]
	assert not [msg for msg in messages if msg["type"] == "server_error"]

	session.close()


def test_queued_route_bound_navigation_is_revalidated_on_reconnect():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	session.disconnect()
	view = session.view_for_path("/a")
	with ps.PulseContext.update(
		render=session,
		route=view.route,
		view=view,
		source_pathname=view.route.pathname,
	):
		ps.navigate("/after")

	session.detach(view.id)
	session.connect(messages.append)

	assert not [msg for msg in messages if msg["type"] == "navigate_to"]

	session.close()


@pytest.mark.asyncio
async def test_later_callback_runs_after_detach_but_route_navigation_is_ignored():
	fired = asyncio.Event()

	@ps.component
	def Page():
		def run_later():
			ps.navigate("/after")
			fired.set()

		def on_click():
			ps.later(0.01, run_later)

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	session.detach(view.id)

	await asyncio.wait_for(fired.wait(), timeout=0.2)
	await asyncio.sleep(0)

	assert not [msg for msg in messages if msg["type"] == "navigate_to"]
	assert not [msg for msg in messages if msg["type"] == "server_error"]

	session.close()


@pytest.mark.asyncio
async def test_disconnect_pauses_render_effects():
	"""Test that RenderSession.disconnect() pauses all route render effects."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	assert root_effect(view) is not None
	assert root_effect(view).paused is False

	# Disconnect should pause the effect (after queue timeout)
	session.disconnect()

	assert session.connected is False
	# Note: now effects transition to PENDING first, not immediately paused
	assert view.state == "pending"

	session.close()


@pytest.mark.asyncio
async def test_reconnect_flushes_queue_when_pending():
	"""Test that reconnecting to an existing session flushes queued messages."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# First connection
	messages1: list[ServerMessage] = []
	session.connect(lambda msg: messages1.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	assert len(messages1) == 0

	# Disconnect - state becomes PENDING
	session.disconnect()
	view = session.view_for_path("/a")
	assert view.state == "pending"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	# Attach again (simulating client reconnection)
	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	# Queue was empty, so no messages sent. State is now ACTIVE.
	assert len(messages2) == 0
	assert view.state == "active"

	session.close()


def test_resume_missing_view_requests_reload():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		ok = session.resume(
			"resume-1",
			[
				{
					"view": "missing-view",
					"routeInfo": make_route_info("/a"),
					"attachId": "attach-1",
				}
			],
			[],
		)

	assert ok is False
	assert messages == [
		{"type": "server_resume", "resumeId": "resume-1", "status": "reload"}
	]

	session.close()


def test_resume_accepts_pending_view_and_flushes_queue_after_snapshot():
	routes = RouteTree([Route("a", StatefulCounter)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))
		attach_view(session, "/a")

	session.disconnect()
	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	session.flush()
	assert view.queue is not None
	assert len(view.queue) == 1

	resume_messages: list[ServerMessage] = []
	session.connect(resume_messages.append)
	with ps.PulseContext.update(render=session):
		ok = session.resume(
			"resume-1",
			[
				{
					"view": view.id,
					"routeInfo": make_route_info("/a"),
					"attachId": "attach-1",
				}
			],
			[],
		)

	assert ok is True
	assert [message["type"] for message in resume_messages] == [
		"vdom_update",
		"server_resume",
	]
	assert resume_messages[1] == {
		"type": "server_resume",
		"resumeId": "resume-1",
		"status": "ok",
		"views": [{"view": view.id, "attachId": "attach-1"}],
		"channels": [],
	}

	session.close()


def test_prerender_of_active_path_queues_updates_until_route_sync():
	routes = make_routes()
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	messages.clear()

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))

	view = session.view_for_path("/a")
	session.execute_callback(view.id, first_callback_key(session, "/a"), [])
	session.flush()

	assert messages == []

	with ps.PulseContext.update(render=session):
		session.update_route(view.id, make_route_info("/a"))

	updates = [message for message in messages if message["type"] == "vdom_update"]
	assert len(updates) == 1

	session.close()


@pytest.mark.asyncio
async def test_messages_dropped_while_disconnected():
	"""Test that messages are dropped (not buffered) while disconnected."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")
	messages.clear()

	view = session.view_for_path("/a")

	# Disconnect
	session.disconnect()

	# Try to send a message while disconnected
	session.send({"type": "vdom_update", "view": view.id, "ops": []})

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	# Message should NOT have been buffered
	assert len(messages2) == 0

	session.close()


@pytest.mark.asyncio
async def test_route_info_updated_on_reconnect():
	"""Test that routeInfo is updated when reconnecting with different params."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	route_info1: RouteInfo = {
		"pathname": "/a",
		"hash": "",
		"query": "foo=bar",
		"queryParams": {"foo": "bar"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], route_info1)
		attach_view(session, "/a", route_info1)

	view = session.view_for_path("/a")
	assert view.route.query == "foo=bar"

	# Disconnect
	session.disconnect()

	# Reconnect with different query params
	session.connect(lambda msg: messages.append(msg))

	route_info2: RouteInfo = {
		"pathname": "/a",
		"hash": "",
		"query": "baz=qux",
		"queryParams": {"baz": "qux"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.attach(view.id, route_info2)

	# Route info should be updated
	assert view.route.query == "baz=qux"

	session.close()


@ps.component
def StatefulCounter():
	with ps.init():
		state = CounterState()

	def increment():
		state.count += 1

	return ps.div()[
		ps.span()[str(state.count)],
		ps.button(onClick=increment)["Increment"],
	]


@pytest.mark.asyncio
async def test_state_preserved_across_reconnect():
	"""Test that state changes are reflected in VDOM after reconnect."""
	routes = RouteTree([Route("a", StatefulCounter)])
	session = RenderSession("test-id", routes)

	# First connection
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], make_route_info("/a"))["/a"]
		attach_view(session, "/a")

	# Should have initial vdom_init with count 0
	assert result["type"] == "vdom_init"
	assert "0" in str(result["vdom"])

	view = session.view_for_path("/a")

	# Execute the increment callback
	session.execute_callback(view.id, "1.onClick", [])
	session.flush()

	# Should have vdom_update
	assert len(messages) == 1
	assert messages[0]["type"] == "vdom_update"

	# Disconnect - state goes to PENDING
	session.disconnect()
	assert view.state == "pending"

	# Execute another increment while disconnected (will be queued)
	session.execute_callback(view.id, "1.onClick", [])
	session.flush()

	# The update should be queued
	assert view.queue is not None
	assert len(view.queue) == 1
	assert view.queue[0]["type"] == "vdom_update"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	# Queue should be flushed - should get the queued vdom_update
	assert len(messages2) == 1
	assert messages2[0]["type"] == "vdom_update"

	# Verify the count is now 2 (two increments)
	vdom = view.tree.render()
	assert "2" in str(vdom)

	session.close()


@pytest.mark.asyncio
async def test_effect_paused_in_idle_state():
	"""Test that effects are paused when view transitions to IDLE state."""
	routes = make_routes()
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	assert root_effect(view) is not None
	assert root_effect(view).paused is False
	assert view.state == "active"

	# Disconnect puts view in PENDING state (not paused)
	session.disconnect()
	assert view.state == "pending"
	assert root_effect(view).paused is False  # Still running in PENDING

	# Manually trigger transition to IDLE (simulating timeout)
	transition_view_to_idle(session, "/a")

	# Now the effect should be paused
	assert view.state == "idle"
	assert root_effect(view).paused is True
	assert root_effect(view).batch is None

	session.close()


@pytest.mark.asyncio
async def test_multiple_routes_idle_attach_requests_reload():
	"""Test that attaching idle routes requests a reload."""
	routes = make_routes()
	session = RenderSession("test-id", routes)

	# First connection - mount both routes
	messages1: list[ServerMessage] = []
	session.connect(lambda msg: messages1.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a", "/b"])
		attach_view(session, "/a")
		attach_view(session, "/b")

	assert len(messages1) == 0

	# Disconnect - goes to PENDING
	session.disconnect()
	view_a = session.view_for_path("/a")
	view_b = session.view_for_path("/b")
	assert view_a.state == "pending"
	assert view_b.state == "pending"

	# Manually transition to IDLE (simulating timeout)
	transition_view_to_idle(session, "/a")
	transition_view_to_idle(session, "/b")

	# Both effects should now be paused
	effect_a = root_effect(view_a)
	effect_b = root_effect(view_b)
	assert effect_a is not None
	assert effect_b is not None
	assert effect_a.paused is True
	assert effect_b.paused is True
	assert view_a.state == "idle"
	assert view_b.state == "idle"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach(view_a.id, make_route_info("/a"))
		session.attach(view_b.id, make_route_info("/b"))

	# Should request reload for each idle attach
	reload_messages = [m for m in messages2 if m["type"] == "reload"]
	assert len(reload_messages) == 2

	# Both effects should remain paused
	assert effect_a.paused is True
	assert effect_b.paused is True
	assert view_a.state == "idle"
	assert view_b.state == "idle"

	session.close()


# =============================================================================
# Timeout and Cancellation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_call_api_timeout():
	"""Test that call_api raises TimeoutError when no response arrives."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, server_address="http://localhost:8000")

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	# Call API with a very short timeout - no response will arrive
	with pytest.raises(asyncio.TimeoutError):
		await session.call_api("/test", timeout=0.01)

	# Verify the pending API was cleaned up
	assert len(session._pending_api) == 0  # pyright: ignore[reportPrivateUsage]

	session.close()


@pytest.mark.asyncio
async def test_call_api_success_before_timeout():
	"""Test that call_api succeeds when response arrives before timeout."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, server_address="http://localhost:8000")

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	# Start the API call
	api_task = asyncio.create_task(session.call_api("/test", timeout=1.0))

	# Give it a moment to send the message
	assert await wait_for(
		lambda: any(m.get("type") == "api_call" for m in messages), timeout=0.2
	)

	# Find the api_call message and get its ID
	api_msgs = [m for m in messages if m.get("type") == "api_call"]
	assert len(api_msgs) == 1
	api_id = cast(Any, api_msgs[0])["id"]

	# Simulate client response
	session.handle_api_result(
		{
			"id": api_id,
			"ok": True,
			"status": 200,
			"headers": {},
			"body": {"success": True},
		}
	)

	# The task should complete successfully
	result = await api_task
	assert result["ok"] is True
	assert result["body"] == {"success": True}

	session.close()


@pytest.mark.asyncio
async def test_run_js_timeout():
	"""Test that run_js future raises TimeoutError when no response arrives."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")

	# Run JS with result=True and short timeout
	with ps.PulseContext.update(render=session, route=view.route, view=view):
		future = session.run_js(get_answer(), result=True, timeout=0.05)

	assert future is not None

	# Wait for timeout
	with pytest.raises(asyncio.TimeoutError):
		await future

	# Verify the pending JS result was cleaned up
	assert len(session._pending_js_results) == 0  # pyright: ignore[reportPrivateUsage]

	session.close()


@pytest.mark.asyncio
async def test_run_js_success_before_timeout():
	"""Test that run_js future resolves when response arrives before timeout."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")

	# Run JS with result=True
	with ps.PulseContext.update(render=session, route=view.route, view=view):
		future = session.run_js(get_answer(), result=True, timeout=1.0)

	assert future is not None

	# Find the js_exec message and get its ID
	js_msgs = [m for m in messages if m.get("type") == "js_exec"]
	assert len(js_msgs) == 1
	exec_id = cast(Any, js_msgs[0])["id"]

	# Simulate client response
	session.handle_js_result({"id": exec_id, "result": 42, "error": None})

	# The future should resolve with the result
	result = await future
	assert result == 42

	session.close()


@pytest.mark.asyncio
async def test_session_close_cancels_pending_api():
	"""Test that session.close() cancels pending API futures."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, server_address="http://localhost:8000")

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	# Create a pending API future manually (simulating an in-flight request)
	loop = asyncio.get_running_loop()
	fut: asyncio.Future[Any] = loop.create_future()
	session._pending_api["test-id"] = fut  # pyright: ignore[reportPrivateUsage]

	# Close the session
	session.close()

	# The future should be cancelled
	assert fut.cancelled()
	assert len(session._pending_api) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_session_close_cancels_pending_js():
	"""Test that session.close() cancels pending JS result futures."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	# Create a pending JS future manually
	loop = asyncio.get_running_loop()
	fut: asyncio.Future[Any] = loop.create_future()
	session._pending_js_results["test-id"] = fut  # pyright: ignore[reportPrivateUsage]

	# Close the session
	session.close()

	# The future should be cancelled
	assert fut.cancelled()
	assert len(session._pending_js_results) == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_session_close_cancels_tracked_tasks():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	started = asyncio.Event()
	cancelled = asyncio.Event()

	async def work():
		started.set()
		try:
			await asyncio.sleep(10)
		except asyncio.CancelledError:
			cancelled.set()
			raise

	session.create_task(work(), name="test.task")
	assert await wait_for(lambda: started.is_set(), timeout=0.2)

	session.close()

	assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)


@pytest.mark.asyncio
async def test_session_close_ignores_cancelled_callback_tasks():
	started = asyncio.Event()
	cancelled = asyncio.Event()

	@ps.component
	def AsyncCallbackComponent():
		async def on_click():
			started.set()
			try:
				await asyncio.sleep(10)
			except asyncio.CancelledError:
				cancelled.set()
				raise

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", AsyncCallbackComponent)])
	session = RenderSession("test-id", routes)

	errors: list[dict[str, Any]] = []
	loop = asyncio.get_running_loop()
	prev_handler = loop.get_exception_handler()

	def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
		errors.append(context)

	loop.set_exception_handler(handler)
	try:
		with ps.PulseContext.update(render=session):
			session.prerender(["/a"])
			attach_view(session, "/a")

		view = session.view_for_path("/a")
		callbacks = view.tree.callbacks
		assert len(callbacks) == 1
		key = next(iter(callbacks))
		session.execute_callback(view.id, key, [])
		assert await wait_for(lambda: started.is_set(), timeout=0.2)

		session.close()

		assert await wait_for(lambda: cancelled.is_set(), timeout=0.2)
		await asyncio.sleep(0)
		assert errors == []
	finally:
		loop.set_exception_handler(prev_handler)


@pytest.mark.asyncio
async def test_session_close_cancels_tracked_timers():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	fired = False

	def on_fire():
		nonlocal fired
		fired = True

	session.schedule_later(0.05, on_fire)
	session.close()

	await asyncio.sleep(0.1)
	assert fired is False


@pytest.mark.asyncio
async def test_session_close_cancels_cleanup_timers():
	class TimerState(ps.State):
		_render: RenderSession | None = None
		fired: bool = False

		def capture_render(self) -> None:
			self._render = ps.PulseContext.get().render

		@override
		def on_dispose(self) -> None:
			render = self._render
			assert render is not None

			def on_fire() -> None:
				self.fired = True

			render.schedule_later(0.05, on_fire)

	state_box: list[TimerState] = []

	@ps.component
	def component():
		state = ps.state(TimerState)
		state.capture_render()
		if not state_box:
			state_box.append(state)
		return ps.div()

	routes = RouteTree([Route("a", component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	assert state_box
	session.close()

	await asyncio.sleep(0.1)
	assert state_box[0].fired is False


def test_handle_api_result_ignores_unknown_id():
	"""Test that handle_api_result silently ignores unknown correlation IDs."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	session.connect(lambda _: None)

	# Should not raise
	session.handle_api_result(
		{"id": "unknown-id", "ok": True, "status": 200, "headers": {}, "body": None}
	)

	session.close()


def test_handle_js_result_ignores_unknown_id():
	"""Test that handle_js_result silently ignores unknown exec IDs."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	session.connect(lambda _: None)

	# Should not raise
	session.handle_js_result({"id": "unknown-id", "result": 42, "error": None})

	session.close()


# =============================================================================
# Prerender and Interrupt Tests
# =============================================================================


@pytest.mark.asyncio
async def test_prerender_renders_once():
	render_calls: list[int] = []

	@ps.component
	def counting_component():
		render_calls.append(1)
		return ps.div()["Hello"]

	routes = RouteTree([Route("a", counting_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], None)["/a"]

	assert result["type"] == "vdom_init"
	assert len(render_calls) == 1

	session.close()


@ps.component
def redirecting_component():
	raise RedirectInterrupt("/other", replace=True)


@ps.component
def not_found_component():
	raise NotFoundInterrupt()


@pytest.mark.asyncio
async def test_prerender_redirect_removes_view():
	"""Test that RedirectInterrupt during first prerender removes the view."""
	routes = RouteTree([Route("redirect", redirecting_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/redirect"], None)["/redirect"]

	# Should return navigate_to message
	assert result["type"] == "navigate_to"
	assert result["path"] == "/other"
	assert result["replace"] is True

	# View should have been disposed after the interrupt
	assert session.views == {}
	with pytest.raises(ValueError):
		session.view_for_path("/redirect")

	session.close()


@pytest.mark.asyncio
async def test_prerender_not_found_removes_view():
	"""Test that NotFoundInterrupt during first prerender removes the view."""
	routes = RouteTree([Route("missing", not_found_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/missing"], None)["/missing"]

	# Should return navigate_to message pointing to app.not_found
	assert result["type"] == "navigate_to"
	assert result["replace"] is True

	# View should have been disposed
	assert session.views == {}
	with pytest.raises(ValueError):
		session.view_for_path("/missing")

	session.close()


@pytest.mark.asyncio
async def test_prerender_then_attach_works():
	"""Test the normal prerender → attach flow."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Prerender first
	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], None)["/a"]

	assert result["type"] == "vdom_init"
	view = session.view_for_path("/a")
	assert result["view"] == view.id
	assert result["routePath"] == "/a"
	assert view.state == "pending"
	assert root_effect(view) is not None  # Effect created during prerender

	# Now attach
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	# Should transition to active, queue flushed (empty)
	assert view.state == "active"
	assert view.queue is None
	assert len(messages) == 0  # No new messages, VDOM already sent during prerender

	session.close()


@pytest.mark.asyncio
async def test_prerender_seeds_effect_deps_for_updates():
	"""Prerender should seed deps so updates fire before the effect runs."""

	class PrerenderCounterState(ps.State):
		count: int = 0

	def prerender_counter():
		state = ps.setup(PrerenderCounterState)

		def inc():
			state.count = state.count + 1

		return ps.div()[
			ps.span()[str(state.count)],
			ps.button(onClick=inc)["inc"],
		]

	routes = RouteTree([Route("a", ps.component(prerender_counter))])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], None)

	view = session.view_for_path("/a")
	assert root_effect(view) is not None
	# The initial render ran inside the effect's dependency capture
	assert root_effect(view).runs == 1

	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	session.execute_callback(view.id, "1.onClick", [])
	session.flush()

	assert len([m for m in messages if m["type"] == "vdom_update"]) == 1

	session.close()


@pytest.mark.asyncio
async def test_prerender_keeps_views_for_unrendered_paths():
	"""Test that prerender preserves views that are not part of the new paths."""
	routes = make_routes()
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a", "/b"])
		attach_view(session, "/a")
		attach_view(session, "/b")

	view_a = session.view_for_path("/a")
	view_b = session.view_for_path("/b")
	effect_a = root_effect(view_a)
	effect_b = root_effect(view_b)
	assert effect_a is not None
	assert effect_b is not None
	assert view_a.state == "active"
	assert view_b.state == "active"

	nav_info = make_route_info("/a")
	nav_info["query"] = "page=2"
	nav_info["queryParams"] = {"page": "2"}

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], nav_info)["/a"]

	assert result["type"] == "vdom_init"
	assert session.view_for_path("/a") is view_a
	assert root_effect(view_a) is effect_a
	assert view_a.state == "pending"
	assert view_a.route.query == "page=2"
	assert session.view_for_path("/b") is view_b
	assert root_effect(view_b) is effect_b

	messages.clear()
	session.update_route(view_a.id, nav_info)
	assert view_a.state == "active"
	session.execute_callback(view_a.id, "1.onClick", [])
	session.flush()

	assert len([m for m in messages if m["type"] == "vdom_update"]) == 1

	session.close()


@pytest.mark.asyncio
async def test_attach_after_redirect_prerender_requests_reload():
	"""Test that attaching after a redirecting prerender requests a reload."""
	# Route that redirects on first render but not subsequent ones
	render_count = {"value": 0}

	@ps.component
	def conditional_redirect():
		render_count["value"] += 1
		if render_count["value"] == 1:
			raise RedirectInterrupt("/other")
		return ps.div()["Success"]

	routes = RouteTree([Route("cond", conditional_redirect)])
	session = RenderSession("test-id", routes)

	# First prerender - redirects, the view is disposed
	with ps.PulseContext.update(render=session):
		result = session.prerender(["/cond"], None)["/cond"]

	assert result["type"] == "navigate_to"
	assert session.views == {}

	# Now attach with the stale id (simulating user navigating back)
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("stale-view", make_route_info("/cond"))

	# Should request reload and not create a view
	assert session.views == {}
	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

	session.close()


@pytest.mark.asyncio
async def test_re_prerender_returns_fresh_vdom():
	"""Test that calling prerender again on same path returns fresh VDOM."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result1 = session.prerender(["/a"], None)["/a"]
		result2 = session.prerender(["/a"], None)["/a"]

	assert result1["type"] == "vdom_init"
	assert result2["type"] == "vdom_init"
	# Both should return valid VDOM
	assert result1["vdom"] is not None
	assert result2["vdom"] is not None

	session.close()


@pytest.mark.asyncio
async def test_detach_immediate_removes_view_and_disposes_effect():
	"""Test that detach immediately removes the view and disposes its effect."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	effect = root_effect(view)
	assert effect is not None

	session.detach(view.id)

	assert view.id not in session.views
	with pytest.raises(ValueError):
		session.view_for_path("/a")
	assert len(effect.deps) == 0
	assert effect.parent is None

	# Attaching the disposed view id again must trigger a reload
	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	assert messages == [{"type": "reload"}]

	session.close()


def test_dev_strict_mode_detach_replay_reuses_view_without_reload():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, dev_strict_mode_detach_timeout=10.0)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	first_view_id = view.id

	session.detach(view.id)

	# The view keeps its id through the dev StrictMode detach grace window
	assert session.view_for_path("/a") is view
	assert session.views[first_view_id] is view
	assert view.state == "pending"
	assert view.pending_action == "dispose"
	assert view.id == first_view_id

	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	assert session.view_for_path("/a") is view
	assert view.state == "active"
	assert not [msg for msg in messages if msg["type"] == "reload"]

	session.close()


@pytest.mark.asyncio
async def test_dev_strict_mode_detach_disposes_after_timeout():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, dev_strict_mode_detach_timeout=0.01)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	view = session.view_for_path("/a")
	session.detach(view.id)

	await wait_for(lambda: view.id not in session.views)

	session.close()


def test_detach_nonexistent_view_is_noop():
	"""Test that detaching a view id that doesn't exist is a no-op."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Should not raise
	session.detach("nonexistent-view")

	session.close()


@pytest.mark.asyncio
async def test_update_route_updates_route_context():
	"""Test that update_route updates the route context for an attached view."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	initial_info: RouteInfo = {
		"pathname": "/a",
		"hash": "",
		"query": "x=1",
		"queryParams": {"x": "1"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], initial_info)
		attach_view(session, "/a", initial_info)

	view = session.view_for_path("/a")
	assert view.route.query == "x=1"

	# Update route
	updated_info: RouteInfo = {
		"pathname": "/a",
		"hash": "section",
		"query": "y=2",
		"queryParams": {"y": "2"},
		"pathParams": {},
		"catchall": [],
	}
	session.update_route(view.id, updated_info)

	assert view.route.query == "y=2"
	assert view.route.hash == "section"

	session.close()


def test_update_route_missing_view_is_noop(monkeypatch: pytest.MonkeyPatch):
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	reported: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		reported.append((args, kwargs))

	monkeypatch.setattr(session, "report_error", report_error)

	session.update_route("missing-view", make_route_info("/missing"))

	assert reported == []

	session.close()


def test_execute_callback_missing_view_is_noop(monkeypatch: pytest.MonkeyPatch):
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	reported: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		reported.append((args, kwargs))

	monkeypatch.setattr(session, "report_error", report_error)

	session.execute_callback("missing-view", "1.onClick", [])

	assert reported == []

	session.close()


def test_execute_callback_stale_key_is_noop(monkeypatch: pytest.MonkeyPatch):
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	reported: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		reported.append((args, kwargs))

	monkeypatch.setattr(session, "report_error", report_error)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		attach_view(session, "/a")

	session.execute_callback(session.view_for_path("/a").id, "missing.onClick", [])

	assert reported == []

	session.close()


@pytest.mark.asyncio
async def test_prerender_queue_timeout_transitions_to_idle():
	"""Test that prerender without attach eventually transitions to idle."""
	routes = RouteTree([Route("a", simple_component)])
	# Very short timeout for testing
	session = RenderSession("test-id", routes, prerender_queue_timeout=0.01)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	view = session.view_for_path("/a")
	assert view.state == "pending"
	assert root_effect(view) is not None
	assert root_effect(view).paused is False

	# Manually trigger the timeout (simulating time passing)
	transition_view_to_idle(session, "/a")

	assert view.state == "idle"
	assert root_effect(view).paused is True

	session.close()


@pytest.mark.asyncio
async def test_attach_from_idle_requests_reload():
	"""Test that attaching to an idle view requests a reload."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Prerender, then transition to idle
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	view = session.view_for_path("/a")
	transition_view_to_idle(session, "/a")
	assert view.state == "idle"
	assert root_effect(view) is not None
	assert root_effect(view).paused is True

	# Now attach
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach(view.id, make_route_info("/a"))

	# Should request reload and leave the view idle
	assert view.state == "idle"
	assert root_effect(view).paused is True
	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

	session.close()
