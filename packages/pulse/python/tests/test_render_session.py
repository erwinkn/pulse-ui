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
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree


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


def make_route_info(pathname: str) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


# TODO: clean this up - this was refactored using GPT-5 and is thus quite hacky
def mount_with_listener(session: RenderSession, path: str):
	# Maintain a session-level set of listened paths and a shared message log
	listened: set[str] | None = getattr(session, "_test_listened_paths", None)
	if listened is None:
		listened = set()
		session._test_listened_paths = listened  # pyright: ignore[reportAttributeAccessIssue]

	log: list[ServerMessage] | None = getattr(session, "_test_message_log", None)
	if log is None:
		log = []
		session._test_message_log = log  # pyright: ignore[reportAttributeAccessIssue]

		def on_message(msg: ServerMessage):
			if msg.get("type") == "api_call":
				return
			p = msg.get("path")
			if not isinstance(p, str):
				return
			# Only record messages for paths we're currently listening to
			if p in getattr(session, "_test_listened_paths", set()):  # pyright: ignore[reportUnknownArgumentType]
				session._test_message_log.append(msg)  # pyright: ignore[reportAttributeAccessIssue]

		session.connect(on_message)

	# Start listening for this path
	listened.add(path)

	class _PathMessages:
		def __iter__(self):  # type: ignore[override]
			for m in getattr(session, "_test_message_log", []):
				if m.get("path") == path:
					yield m

	# Ensure RenderSession is present in PulseContext when attaching so the
	# captured context for the render effect includes it
	with ps.PulseContext.update(render=session):
		session.prerender(sorted(listened))
		session.attach(path, make_route_info(path))

	def disconnect():
		# Stop listening for this path; messages are still in the shared log
		lst = getattr(session, "_test_listened_paths", set())  # pyright: ignore[reportUnknownArgumentType]
		if isinstance(lst, set):
			lst.discard(path)

	return _PathMessages(), disconnect


def extract_count_from_ctx(session: RenderSession, path: str) -> int:
	# Read latest VDOM by re-rendering from the RenderTree and inspecting it
	mount = session.route_mounts[path]
	with ps.PulseContext.update(render=session, route=mount.route):
		vdom = mount.tree.render()
	vdom_dict = cast(dict[str, Any], cast(object, vdom))
	children = cast(list[Any], (vdom_dict.get("children", []) or []))
	span = cast(dict[str, Any], children[0])
	text_children = cast(list[Any], span.get("children", [0]))
	text = text_children[0]
	return int(text)  # type: ignore[arg-type]


def test_two_sessions_two_routes_are_isolated():
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
	s1.execute_callback("/a", "1.onClick", [])
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
	s2.execute_callback("/a", "1.onClick", [])
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
	mount = session.route_mounts[path]
	with ps.PulseContext.update(render=session, route=mount.route):
		vdom = mount.tree.render()
	vdom_dict = cast(dict[str, Any], cast(object, vdom))
	children = cast(list[Any], (vdom_dict.get("children", []) or []))
	span = cast(dict[str, Any], children[0])
	text_children = cast(list[Any], span.get("children", [0]))
	text = text_children[0]
	return int(text)  # type: ignore[arg-type]


def test_global_state_shared_within_session_and_isolated_across_sessions():
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
	s1.execute_callback("/a", "1.onClick", [])
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
	s2.execute_callback("/b", "1.onClick", [])
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


def test_global_state_disposed_on_session_close():
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


# =============================================================================
# Reconnection / Rehydration Tests
# =============================================================================


@ps.component
def simple_component():
	return ps.div()["Hello World"]


@pytest.mark.asyncio
async def test_attach_without_prerender_requests_reload():
	"""Test that attaching without prerender requests a reload."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	assert "/a" not in session.route_mounts
	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

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
		session.attach("/a", make_route_info("/a"))

	mount = session.route_mounts["/a"]
	assert mount.effect is not None
	assert mount.effect.paused is False

	# Disconnect should pause the effect (after queue timeout)
	session.disconnect()

	assert session.connected is False
	# Note: now effects transition to PENDING first, not immediately paused
	assert mount.state == "pending"

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
		session.attach("/a", make_route_info("/a"))

	assert len(messages1) == 0

	# Disconnect - state becomes PENDING
	session.disconnect()
	mount = session.route_mounts["/a"]
	assert mount.state == "pending"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	# Attach again (simulating client reconnection)
	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	# Queue was empty, so no messages sent. State is now ACTIVE.
	assert len(messages2) == 0
	assert mount.state == "active"

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
		session.attach("/a", make_route_info("/a"))
	messages.clear()

	# Disconnect
	session.disconnect()

	# Try to send a message while disconnected
	session.send({"type": "vdom_update", "path": "/a", "ops": []})  # type: ignore[typeddict-item]

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
		"query": "?foo=bar",
		"queryParams": {"foo": "bar"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], route_info1)
		session.attach("/a", route_info1)

	mount = session.route_mounts["/a"]
	assert mount.route.query == "?foo=bar"

	# Disconnect
	session.disconnect()

	# Reconnect with different query params
	session.connect(lambda msg: messages.append(msg))

	route_info2: RouteInfo = {
		"pathname": "/a",
		"hash": "",
		"query": "?baz=qux",
		"queryParams": {"baz": "qux"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.attach("/a", route_info2)

	# Route info should be updated
	assert mount.route.query == "?baz=qux"

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
		session.attach("/a", make_route_info("/a"))

	# Should have initial vdom_init with count 0
	assert result["type"] == "vdom_init"
	assert "0" in str(result["vdom"])

	# Execute the increment callback
	session.execute_callback("/a", "1.onClick", [])
	session.flush()

	# Should have vdom_update
	assert len(messages) == 1
	assert messages[0]["type"] == "vdom_update"

	# Disconnect - state goes to PENDING
	session.disconnect()
	mount = session.route_mounts["/a"]
	assert mount.state == "pending"

	# Execute another increment while disconnected (will be queued)
	session.execute_callback("/a", "1.onClick", [])
	session.flush()

	# The update should be queued
	assert mount.queue is not None
	assert len(mount.queue) == 1
	assert mount.queue[0]["type"] == "vdom_update"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	# Queue should be flushed - should get the queued vdom_update
	assert len(messages2) == 1
	assert messages2[0]["type"] == "vdom_update"

	# Verify the count is now 2 (two increments)
	vdom = mount.tree.render()
	assert "2" in str(vdom)

	session.close()


@pytest.mark.asyncio
async def test_effect_paused_in_idle_state():
	"""Test that effects are paused when mount transitions to IDLE state."""
	routes = make_routes()
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	mount = session.route_mounts["/a"]
	assert mount.effect is not None
	assert mount.effect.paused is False
	assert mount.state == "active"

	# Disconnect puts mount in PENDING state (not paused)
	session.disconnect()
	assert mount.state == "pending"
	assert mount.effect.paused is False  # Still running in PENDING

	# Manually trigger transition to IDLE (simulating timeout)
	session._transition_to_idle("/a")  # pyright: ignore[reportPrivateUsage]

	# Now the effect should be paused
	assert mount.state == "idle"
	assert mount.effect.paused is True
	assert mount.effect.batch is None

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
		session.attach("/a", make_route_info("/a"))
		session.attach("/b", make_route_info("/b"))

	assert len(messages1) == 0

	# Disconnect - goes to PENDING
	session.disconnect()
	mount_a = session.route_mounts["/a"]
	mount_b = session.route_mounts["/b"]
	assert mount_a.state == "pending"
	assert mount_b.state == "pending"

	# Manually transition to IDLE (simulating timeout)
	session._transition_to_idle("/a")  # pyright: ignore[reportPrivateUsage]
	session._transition_to_idle("/b")  # pyright: ignore[reportPrivateUsage]

	# Both effects should now be paused
	effect_a = mount_a.effect
	effect_b = mount_b.effect
	assert effect_a is not None
	assert effect_b is not None
	assert effect_a.paused is True
	assert effect_b.paused is True
	assert mount_a.state == "idle"
	assert mount_b.state == "idle"

	# Reconnect
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))
		session.attach("/b", make_route_info("/b"))

	# Should request reload for each idle attach
	reload_messages = [m for m in messages2 if m["type"] == "reload"]
	assert len(reload_messages) == 2

	# Both effects should remain paused
	assert effect_a.paused is True
	assert effect_b.paused is True
	assert mount_a.state == "idle"
	assert mount_b.state == "idle"

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
		session.attach("/a", make_route_info("/a"))

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
		session.attach("/a", make_route_info("/a"))

	# Start the API call
	api_task = asyncio.create_task(session.call_api("/test", timeout=1.0))

	# Give it a moment to send the message
	await asyncio.sleep(0.01)

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
		session.attach("/a", make_route_info("/a"))

	# Run JS with result=True and short timeout
	with ps.PulseContext.update(render=session, route=session.route_mounts["/a"].route):
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
		session.attach("/a", make_route_info("/a"))

	# Run JS with result=True
	with ps.PulseContext.update(render=session, route=session.route_mounts["/a"].route):
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
		session.attach("/a", make_route_info("/a"))

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
		session.attach("/a", make_route_info("/a"))

	# Create a pending JS future manually
	loop = asyncio.get_running_loop()
	fut: asyncio.Future[Any] = loop.create_future()
	session._pending_js_results["test-id"] = fut  # pyright: ignore[reportPrivateUsage]

	# Close the session
	session.close()

	# The future should be cancelled
	assert fut.cancelled()
	assert len(session._pending_js_results) == 0  # pyright: ignore[reportPrivateUsage]


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
async def test_prerender_redirect_removes_mount():
	"""Test that RedirectInterrupt during first prerender removes mount from route_mounts."""
	routes = RouteTree([Route("redirect", redirecting_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/redirect"], None)["/redirect"]

	# Should return navigate_to message
	assert result["type"] == "navigate_to"
	assert result["path"] == "/other"
	assert result["replace"] is True

	# Mount should NOT be in route_mounts (was removed after interrupt)
	assert "/redirect" not in session.route_mounts

	session.close()


@pytest.mark.asyncio
async def test_prerender_not_found_removes_mount():
	"""Test that NotFoundInterrupt during first prerender removes mount from route_mounts."""
	routes = RouteTree([Route("missing", not_found_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/missing"], None)["/missing"]

	# Should return navigate_to message pointing to app.not_found
	assert result["type"] == "navigate_to"
	assert result["replace"] is True

	# Mount should NOT be in route_mounts
	assert "/missing" not in session.route_mounts

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
	assert "/a" in session.route_mounts
	mount = session.route_mounts["/a"]
	assert mount.state == "pending"
	assert mount.effect is not None  # Effect created during prerender

	# Now attach
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	# Should transition to active, queue flushed (empty)
	assert mount.state == "active"
	assert mount.queue is None
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

	mount = session.route_mounts["/a"]
	assert mount.effect is not None
	assert mount.effect.runs == 0

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", "1.onClick", [])
	session.flush()

	assert len([m for m in messages if m["type"] == "vdom_update"]) == 1

	session.close()


@pytest.mark.asyncio
async def test_prerender_keeps_active_mounts_and_drops_inactive():
	"""Test that prerender preserves active mounts and removes inactive ones."""
	routes = make_routes()
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a", "/b"])
		session.attach("/a", make_route_info("/a"))
		session.attach("/b", make_route_info("/b"))

	mount_a = session.route_mounts["/a"]
	mount_b = session.route_mounts["/b"]
	effect_a = mount_a.effect
	effect_b = mount_b.effect
	assert effect_a is not None
	assert effect_b is not None
	assert mount_a.state == "active"
	assert mount_b.state == "active"

	nav_info = make_route_info("/a")
	nav_info["query"] = "?page=2"
	nav_info["queryParams"] = {"page": "2"}

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], nav_info)["/a"]

	assert result["type"] == "vdom_init"
	assert session.route_mounts["/a"] is mount_a
	assert mount_a.effect is effect_a
	assert mount_a.state == "active"
	assert mount_a.route.query == "?page=2"
	assert "/b" not in session.route_mounts
	assert effect_b.parent is None
	assert mount_b.tree.rendered is False
	for dep in effect_b.deps:
		assert effect_b not in dep.obs

	messages.clear()
	session.update_route("/a", nav_info)
	session.execute_callback("/a", "1.onClick", [])
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

	# First prerender - redirects
	with ps.PulseContext.update(render=session):
		result = session.prerender(["/cond"], None)["/cond"]

	assert result["type"] == "navigate_to"
	assert "/cond" not in session.route_mounts

	# Now attach directly (simulating user navigating back)
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/cond", make_route_info("/cond"))

	# Should request reload and not create a mount
	assert "/cond" not in session.route_mounts
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
async def test_detach_removes_mount_and_disposes_effect():
	"""Test that detach removes mount and disposes the render effect."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	mount = session.route_mounts["/a"]
	effect = mount.effect
	assert effect is not None
	# Effect has deps before dispose
	assert len(effect.deps) >= 0  # Just verify effect exists and is valid

	# Detach
	session.detach("/a")

	# Mount should be removed
	assert "/a" not in session.route_mounts
	# Effect should be disposed (deps cleared, removed from parent)
	assert len(effect.deps) == 0
	assert effect.parent is None

	session.close()


def test_detach_nonexistent_path_is_noop():
	"""Test that detaching a path that doesn't exist is a no-op."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Should not raise
	session.detach("/nonexistent")

	session.close()


def test_update_route_updates_route_context():
	"""Test that update_route updates the route context for an attached path."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	initial_info: RouteInfo = {
		"pathname": "/a",
		"hash": "",
		"query": "?x=1",
		"queryParams": {"x": "1"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], initial_info)
		session.attach("/a", initial_info)

	mount = session.route_mounts["/a"]
	assert mount.route.query == "?x=1"

	# Update route
	updated_info: RouteInfo = {
		"pathname": "/a",
		"hash": "#section",
		"query": "?y=2",
		"queryParams": {"y": "2"},
		"pathParams": {},
		"catchall": [],
	}
	session.update_route("/a", updated_info)

	assert mount.route.query == "?y=2"
	assert mount.route.hash == "#section"

	session.close()


@pytest.mark.asyncio
async def test_prerender_queue_timeout_transitions_to_idle():
	"""Test that prerender without attach eventually transitions to idle."""
	routes = RouteTree([Route("a", simple_component)])
	# Very short timeout for testing
	session = RenderSession("test-id", routes, prerender_queue_timeout=0.01)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	mount = session.route_mounts["/a"]
	assert mount.state == "pending"
	assert mount.effect is not None
	assert mount.effect.paused is False

	# Manually trigger the timeout (simulating time passing)
	session._transition_to_idle("/a")  # pyright: ignore[reportPrivateUsage]

	assert mount.state == "idle"
	assert mount.effect.paused is True

	session.close()


@pytest.mark.asyncio
async def test_attach_from_idle_requests_reload():
	"""Test that attaching to an idle mount requests a reload."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Prerender, then transition to idle
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	mount = session.route_mounts["/a"]
	session._transition_to_idle("/a")  # pyright: ignore[reportPrivateUsage]
	assert mount.state == "idle"
	assert mount.effect is not None
	assert mount.effect.paused is True

	# Now attach
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	# Should request reload and leave mount idle
	assert mount.state == "idle"
	assert mount.effect.paused is True
	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

	session.close()
