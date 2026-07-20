"""
Integration-ish tests for session isolation.

We spin up a minimal route tree with two routes and create two sessions.
Each session mounts both routes and mutates state via callbacks. We assert
that updates from one session do not leak into the other.
"""

import asyncio
import gc
from collections.abc import Callable, Iterator
from typing import Any, Literal, cast, override

import pulse as ps
import pytest
from pulse import javascript
from pulse.hooks.core import HookContext
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import ServerMessage
from pulse.reactive import Effect
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.test_helpers import wait_for
from pulse.transpiler.nodes import Element, PulseNode


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


def expire_pending_mount(session: RenderSession, path: str) -> None:
	"""Simulate the pending-queue timer firing for a mount."""
	session.route_mounts[path]._on_pending_timeout()  # pyright: ignore[reportPrivateUsage]


class PathMessages:
	messages: list[ServerMessage]
	path: str

	def __init__(self, messages: list[ServerMessage], path: str) -> None:
		self.messages = messages
		self.path = path

	def __iter__(self) -> Iterator[ServerMessage]:
		for message in self.messages:
			if message.get("path") == self.path:
				yield message


class RouteMessageLog:
	session: RenderSession
	listened_paths: set[str]
	messages: list[ServerMessage]

	def __init__(self, session: RenderSession) -> None:
		self.session = session
		self.listened_paths = set()
		self.messages = []
		self.session.connect(self._record)

	def _record(self, message: ServerMessage) -> None:
		if message.get("type") == "api_call":
			return
		path = message.get("path")
		if isinstance(path, str) and path in self.listened_paths:
			self.messages.append(message)

	def mount(self, path: str) -> tuple[PathMessages, Callable[[], None]]:
		self.listened_paths.add(path)
		with ps.PulseContext.update(render=self.session):
			self.session.prerender(sorted(self.listened_paths))
			self.session.attach(path, make_route_info(path))

		def disconnect() -> None:
			self.listened_paths.discard(path)

		return PathMessages(self.messages, path), disconnect


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


def first_callback_key(session: RenderSession, path: str) -> str:
	return next(iter(session.route_mounts[path].tree.callbacks))


@pytest.mark.asyncio
async def test_pulse_context_update_can_clear_route_source():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	route = session.route_mounts["/a"].route
	with ps.PulseContext.update(
		render=session,
		route=route,
		source_route_path=route.route_path,
		source_path=route.pathname,
		source_mount_id=session.route_mounts["/a"].mount_id,
	):
		with ps.PulseContext.update(
			route=None,
			source_route_path=None,
			source_path=None,
			source_mount_id=None,
		):
			ctx = ps.PulseContext.get()
			assert ctx.route is None
			assert ctx.source_route_path is None
			assert ctx.source_path is None
			assert ctx.source_mount_id is None

	session.close()


@pytest.mark.asyncio
async def test_two_sessions_two_routes_are_isolated():
	routes = make_routes()
	s1 = RenderSession("s1", routes)
	s2 = RenderSession("s2", routes)
	log_s1 = RouteMessageLog(s1)
	log_s2 = RouteMessageLog(s2)

	# Mount both routes on both sessions and keep listeners active
	msgs_s1_a, disc_s1_a = log_s1.mount("/a")
	msgs_s1_b, disc_s1_b = log_s1.mount("/b")
	msgs_s2_a, disc_s2_a = log_s2.mount("/a")
	msgs_s2_b, disc_s2_b = log_s2.mount("/b")

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


@pytest.mark.asyncio
async def test_global_state_shared_within_session_and_isolated_across_sessions():
	routes = make_global_routes()
	s1 = RenderSession("s1", routes)
	s2 = RenderSession("s2", routes)
	log_s1 = RouteMessageLog(s1)
	log_s2 = RouteMessageLog(s2)

	# Mount both routes on both sessions
	msgs_s1_a, disc_s1_a = log_s1.mount("/a")
	msgs_s1_b, disc_s1_b = log_s1.mount("/b")
	msgs_s2_a, disc_s2_a = log_s2.mount("/a")
	msgs_s2_b, disc_s2_b = log_s2.mount("/b")

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
	log = RouteMessageLog(s)
	_msgs, disc = log.mount("/a")
	# Ensure instance is created by rendering
	assert extract_count_from_ctx(s, "/a") == 0

	# Close session -> should dispose the global singleton instance
	disc()
	s.close()
	assert disposed == ["ok"]


def test_dummy_placeholder_to_keep_line_numbers_stable():
	# Placeholder after revert; keep file stable
	assert True


def test_global_navigate_to_bypasses_pending_mount_queue():
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
		session.attach("/a", make_route_info("/a"))
		session.attach("/a/b", make_route_info("/a/b"))

	mount = session.route_mounts["/a/b"]
	mount.start_pending(10)
	assert mount.state == "pending"
	assert mount.queue == []

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
	assert mount.queue == []

	session.close()


def test_navigate_to_queued_as_global_on_disconnect():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

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
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach("/a")
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
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach("/a")
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
		session.attach("/items/:id", route_info)

	session.execute_callback(
		"/items/:id",
		first_callback_key(session, "/items/:id"),
		[],
	)

	navigations = [msg for msg in messages if msg["type"] == "navigate_to"]
	assert len(navigations) == 1
	assert navigations[0]["path"] == "/after"
	assert navigations[0].get("sourceRoutePath") == "/items/:id"
	assert navigations[0].get("sourcePath") == "/items/123"
	assert isinstance(navigations[0].get("sourceMountId"), str)

	session.close()


def test_route_bound_navigation_validates_source_route_identity():
	routes = RouteTree([Route("a", simple_component), Route("b", simple_component)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	route_info = make_route_info("/shared")

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], route_info)
		session.attach("/a", route_info)
		session.prerender(["/b"], route_info)
		session.attach("/b", route_info)

	mount = session.route_mounts["/a"]
	with ps.PulseContext.update(
		render=session,
		route=mount.route,
		source_route_path=mount.route.route_path,
		source_path=mount.route.pathname,
	):
		session.detach("/a")
		ps.navigate("/after")

	assert "/b" in session.route_mounts
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
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	await started.wait()
	session.detach("/a")

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

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
		session.attach("/items/:id", first_info)

	session.execute_callback(
		"/items/:id", first_callback_key(session, "/items/:id"), []
	)
	await started.wait()
	session.attach("/items/:id", next_info)
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
		session.attach("/a", make_route_info("/a"))

	session.disconnect()
	mount = session.route_mounts["/a"]
	with ps.PulseContext.update(
		render=session,
		route=mount.route,
		source_route_path=mount.route.route_path,
		source_path=mount.route.pathname,
	):
		ps.navigate("/after")

	session.detach("/a")
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
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	session.detach("/a")

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


def test_prerender_of_active_path_queues_updates_until_route_sync():
	routes = make_routes()
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	messages.clear()

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	session.flush()

	assert messages == []

	with ps.PulseContext.update(render=session):
		session.update_route("/a", make_route_info("/a"))

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
		"query": "foo=bar",
		"queryParams": {"foo": "bar"},
		"pathParams": {},
		"catchall": [],
	}
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], route_info1)
		session.attach("/a", route_info1)

	mount = session.route_mounts["/a"]
	assert mount.route.query == "foo=bar"

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
		session.attach("/a", route_info2)

	# Route info should be updated
	assert mount.route.query == "baz=qux"

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
async def test_mount_suspended_after_disconnect_timeout():
	"""Attached mounts suspend (tree kept, rendering paused) when the queue times out."""
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

	# Disconnect puts mount in PENDING state (still rendering + queuing)
	session.disconnect()
	assert mount.state == "pending"
	assert mount.effect.paused is False

	# Simulate the disconnect queue timeout firing
	expire_pending_mount(session, "/a")

	# The mount is suspended: rendering paused, queue dropped, tree retained
	assert session.route_mounts["/a"] is mount
	assert mount.state == "suspended"
	assert mount.effect.paused is True
	assert mount.queue is None
	assert mount.tree.rendered is True

	session.close()


@pytest.mark.asyncio
async def test_attach_resumes_suspended_mounts_with_fresh_init():
	"""Re-attaching suspended mounts sends a fresh vdom_init instead of a reload."""
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

	# Disconnect, then let the queue time out
	session.disconnect()
	expire_pending_mount(session, "/a")
	expire_pending_mount(session, "/b")
	mount_a = session.route_mounts["/a"]
	mount_b = session.route_mounts["/b"]
	assert mount_a.state == "suspended"
	assert mount_b.state == "suspended"

	# Reconnect and re-attach
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))

	with ps.PulseContext.update(render=session):
		assert session.attach("/a", make_route_info("/a")) is True
		assert session.attach("/b", make_route_info("/b")) is True

	assert [m["type"] for m in messages2] == ["vdom_init", "vdom_init"]
	assert mount_a.state == "active"
	assert mount_b.state == "active"
	assert mount_a.effect is not None and mount_a.effect.paused is False
	assert mount_b.effect is not None and mount_b.effect.paused is False

	session.close()


@pytest.mark.asyncio
async def test_suspend_resume_preserves_state():
	"""Component state survives a disconnect that outlives the message queue."""
	routes = RouteTree([Route("a", StatefulCounter)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", "1.onClick", [])
	session.flush()

	# Disconnect long enough for the mount to suspend
	session.disconnect()
	expire_pending_mount(session, "/a")
	assert session.route_mounts["/a"].state == "suspended"

	# State written while suspended is reflected on resume
	session.execute_callback("/a", "1.onClick", [])
	session.flush()

	# Reconnect: attach resumes with a fresh init carrying the current count
	messages2: list[ServerMessage] = []
	session.connect(lambda msg: messages2.append(msg))
	with ps.PulseContext.update(render=session):
		assert session.attach("/a", make_route_info("/a")) is True

	assert len(messages2) == 1
	init = messages2[0]
	assert init["type"] == "vdom_init"
	assert "2" in str(init["vdom"])

	# Callbacks keep working after resume
	session.execute_callback("/a", "1.onClick", [])
	session.flush()
	assert any(m["type"] == "vdom_update" for m in messages2[1:])

	session.close()


# =============================================================================
# Timeout and Cancellation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_call_api_timeout():
	"""Test that call_api raises TimeoutError when no response arrives."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

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
@pytest.mark.parametrize(
	("url", "credentials"),
	[
		("/test", "same-origin"),
		("https://api.example.com/test", "include"),
	],
)
async def test_call_api_success_before_timeout(
	url: str, credentials: Literal["same-origin", "include"]
):
	"""Test that call_api succeeds when response arrives before timeout."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	# Start the API call
	api_task = asyncio.create_task(
		session.call_api(url, credentials=credentials, timeout=1.0)
	)

	# Give it a moment to send the message
	assert await wait_for(
		lambda: any(m.get("type") == "api_call" for m in messages), timeout=0.2
	)

	# Find the api_call message and get its ID
	api_msgs = [m for m in messages if m.get("type") == "api_call"]
	assert len(api_msgs) == 1
	api_msg = cast(Any, api_msgs[0])
	assert api_msg["url"] == url
	assert api_msg["credentials"] == credentials
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
	session = RenderSession("test-id", routes)

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
			session.attach("/a", make_route_info("/a"))

		callbacks = session.route_mounts["/a"].tree.callbacks
		assert len(callbacks) == 1
		key = next(iter(callbacks))
		session.execute_callback("/a", key, [])
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
		session.attach("/a", make_route_info("/a"))

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
async def test_prerender_keeps_mounts_for_unrendered_paths():
	"""Test that prerender preserves mounts that are not part of the new paths."""
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
	nav_info["query"] = "page=2"
	nav_info["queryParams"] = {"page": "2"}

	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], nav_info)["/a"]

	assert result["type"] == "vdom_init"
	assert session.route_mounts["/a"] is mount_a
	assert mount_a.effect is effect_a
	assert mount_a.state == "pending"
	assert mount_a.route.query == "page=2"
	assert session.route_mounts["/b"] is mount_b
	assert mount_b.effect is effect_b

	messages.clear()
	session.update_route("/a", nav_info)
	assert mount_a.state == "active"
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
async def test_detach_immediate_removes_mount_and_disposes_effect():
	"""Test that detach immediately removes the mount and disposes its effect."""
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

	session.detach("/a")

	assert "/a" not in session.route_mounts
	assert len(effect.deps) == 0
	assert effect.parent is None

	session.close()


def test_dev_strict_mode_detach_replay_reuses_mount_without_reload():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, dev_strict_mode_detach_timeout=10.0)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	mount = session.route_mounts["/a"]
	first_mount_id = mount.mount_id

	session.detach("/a")

	assert session.route_mounts["/a"] is mount
	assert mount.state == "pending"
	assert mount.mount_id != first_mount_id

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	assert session.route_mounts["/a"] is mount
	assert mount.state == "active"
	assert not [msg for msg in messages if msg["type"] == "reload"]

	session.close()


@pytest.mark.asyncio
async def test_dev_strict_mode_detach_disposes_after_timeout():
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes, dev_strict_mode_detach_timeout=0.01)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	session.detach("/a")

	await wait_for(lambda: "/a" not in session.route_mounts)

	session.close()


def test_detach_nonexistent_path_is_noop():
	"""Test that detaching a path that doesn't exist is a no-op."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Should not raise
	session.detach("/nonexistent")

	session.close()


@pytest.mark.asyncio
async def test_update_route_updates_route_context():
	"""Test that update_route updates the route context for an attached path."""
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
		session.attach("/a", initial_info)

	mount = session.route_mounts["/a"]
	assert mount.route.query == "x=1"

	# Update route
	updated_info: RouteInfo = {
		"pathname": "/a",
		"hash": "section",
		"query": "y=2",
		"queryParams": {"y": "2"},
		"pathParams": {},
		"catchall": [],
	}
	session.update_route("/a", updated_info)

	assert mount.route.query == "y=2"
	assert mount.route.hash == "section"

	session.close()


def test_update_route_missing_mount_is_noop(monkeypatch: pytest.MonkeyPatch):
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	reported: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		reported.append((args, kwargs))

	monkeypatch.setattr(session, "report_error", report_error)

	session.update_route("/missing", make_route_info("/missing"))

	assert reported == []

	session.close()


def test_execute_callback_missing_mount_is_noop(monkeypatch: pytest.MonkeyPatch):
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)
	reported: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		reported.append((args, kwargs))

	monkeypatch.setattr(session, "report_error", report_error)

	session.execute_callback("/missing", "1.onClick", [])

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
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", "missing.onClick", [])

	assert reported == []

	session.close()


@pytest.mark.asyncio
async def test_prerender_queue_timeout_disposes_mount():
	"""Prerender without attach disposes the mount once the queue times out."""
	routes = RouteTree([Route("a", simple_component)])
	# Very short timeout for testing
	session = RenderSession("test-id", routes, prerender_queue_timeout=0.01)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	mount = session.route_mounts["/a"]
	assert mount.state == "pending"
	assert mount.effect is not None
	assert mount.effect.paused is False

	await asyncio.sleep(0.05)

	assert "/a" not in session.route_mounts
	assert mount.state == "closed"
	assert mount.tree.rendered is False

	session.close()


@pytest.mark.asyncio
async def test_attach_after_dispose_requests_reload():
	"""Attaching to a disposed mount requests a reload."""
	routes = RouteTree([Route("a", simple_component)])
	session = RenderSession("test-id", routes)

	# Prerender, then expire the pending queue
	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])

	mount = session.route_mounts["/a"]
	expire_pending_mount(session, "/a")
	assert mount.state == "closed"
	assert "/a" not in session.route_mounts

	# Now attach
	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.attach("/a", make_route_info("/a"))

	assert len(messages) == 1
	assert messages[0]["type"] == "reload"

	session.close()


@pytest.mark.asyncio
async def test_rerender_does_not_accumulate_objects():
	"""Re-rendering a mounted route many times must not retain per-render objects.

	Long-lived sessions (dashboards, polling pages) re-render thousands of times;
	any per-render retention in the renderer/transpiler/hooks would balloon a
	single session over hours.
	"""
	routes = RouteTree([Route("a", StatefulCounter)])
	session = RenderSession("test-id", routes)
	session.connect(lambda msg: None)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))
		session.attach("/a", make_route_info("/a"))

	def rerender_once():
		session.execute_callback("/a", "1.onClick", [])
		session.flush()

	tracked = (Element, PulseNode, HookContext, Effect)

	def census() -> dict[str, int]:
		gc.collect()
		counts = dict.fromkeys((cls.__name__ for cls in tracked), 0)
		for obj in gc.get_objects():
			name = type(obj).__name__
			if type(obj) in tracked:
				counts[name] += 1
		return counts

	# Warm up so caches and hook state reach steady state
	for _ in range(5):
		rerender_once()
	baseline = census()

	for _ in range(50):
		rerender_once()
	after = census()

	assert after == baseline

	session.close()


class ChildCounterState(ps.State):
	count: int = 0


@ps.component
def NestedChild():
	with ps.init():
		state = ChildCounterState()

	def bump():
		state.count += 1

	return ps.span(onClick=bump)[str(state.count)]


@ps.component
def NestedParent():
	return ps.div()[NestedChild()]


@pytest.mark.asyncio
async def test_reprerender_preserves_child_component_state():
	"""Re-prerendering a mounted route must reconcile, not rebuild child hook state."""
	routes = RouteTree([Route("a", NestedParent)])
	session = RenderSession("test-id", routes)

	messages: list[ServerMessage] = []
	session.connect(lambda msg: messages.append(msg))

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))
		session.attach("/a", make_route_info("/a"))

	# Bump the child component's state
	session.execute_callback("/a", "0.onClick", [])
	session.flush()

	# Re-prerender the mounted route (client-side navigation re-init)
	with ps.PulseContext.update(render=session):
		result = session.prerender(["/a"], make_route_info("/a"))["/a"]

	assert result["type"] == "vdom_init"
	assert "1" in str(result["vdom"])

	session.close()


@pytest.mark.asyncio
async def test_reprerender_does_not_accumulate_objects():
	"""Repeated re-prerenders of a mounted route must not leak hook state.

	Client-side navigations re-prerender mounted routes (e.g. layouts); each
	one used to rebuild child components, stranding their old hook effects.
	"""
	routes = RouteTree([Route("a", NestedParent)])
	session = RenderSession("test-id", routes)
	session.connect(lambda msg: None)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"], make_route_info("/a"))
		session.attach("/a", make_route_info("/a"))

	def reprerender_once():
		with ps.PulseContext.update(render=session):
			session.prerender(["/a"], make_route_info("/a"))
			session.attach("/a", make_route_info("/a"))

	tracked = (Element, PulseNode, HookContext, Effect)

	def census() -> dict[str, int]:
		gc.collect()
		counts = dict.fromkeys((cls.__name__ for cls in tracked), 0)
		for obj in gc.get_objects():
			if type(obj) in tracked:
				counts[type(obj).__name__] += 1
		return counts

	for _ in range(3):
		reprerender_once()
	baseline = census()

	for _ in range(20):
		reprerender_once()
	after = census()

	assert after == baseline

	session.close()


@pytest.mark.asyncio
async def test_async_callback_error_reports_real_traceback():
	"""An async callback that raises is reported from a task done-callback —
	outside any `except` block — so report_error must still produce a real
	stack (not the "NoneType: None" that traceback.format_exc() would give)."""

	@ps.component
	def Page():
		async def on_click():
			raise ValueError("async boom")

		return ps.button(onClick=on_click)["go"]

	routes = RouteTree([Route("a", Page)])
	session = RenderSession("test-id", routes)
	messages: list[ServerMessage] = []
	session.connect(messages.append)

	with ps.PulseContext.update(render=session):
		session.prerender(["/a"])
		session.attach("/a", make_route_info("/a"))

	session.execute_callback("/a", first_callback_key(session, "/a"), [])
	await wait_for(lambda: any(m["type"] == "server_error" for m in messages))

	errors = [m for m in messages if m["type"] == "server_error"]
	assert len(errors) == 1
	err = cast(Any, errors[0])["error"]
	assert err["phase"] == "callback"
	assert err["details"]["async"] is True
	assert "async boom" in err["stack"]
	assert "ValueError" in err["stack"]
	assert "NoneType: None" not in err["stack"]

	session.close()
