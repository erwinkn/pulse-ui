"""
Integration-ish tests for session isolation.

We spin up a minimal route tree with two routes and create two sessions.
Each session mounts both routes and mutates state via callbacks. We assert
that updates from one session do not leak into the other.
"""

from typing import cast

import pulse as ps
from pulse.messages import (
    RouteInfo,
    ServerMessage,
)
from pulse.routing import Route, RouteTree
from pulse.session import Session
from pulse.vdom import VDOM


class CounterState(ps.State):
    count: int = 0

    @ps.effect
    def on_change(self):
        _ = self.count  # track


def Counter(session_name: str, key_prefix: str):
    state = ps.states(CounterState)

    def inc():
        state.count = state.count + 1

    print(f"Rendering counter {key_prefix}:{session_name} with count {state.count}")

    # Render current count + a callback
    return ps.div(key=f"{key_prefix}:{session_name}")[
        ps.span(id=f"count-{session_name}")[str(state.count)],
        ps.button(onClick=inc)["inc"],
    ]


def make_routes() -> RouteTree:
    route_a = Route("a", lambda: Counter("A", "route-a"))
    route_b = Route("b", lambda: Counter("B", "route-b"))
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


def mount_with_listener(session: Session, path: str):
    messages: list[ServerMessage] = []

    def on_message(msg: ServerMessage):
        if msg["type"] == "api_call" or msg["path"] != path:
            return
        messages.append(msg)

    disconnect = session.connect(on_message)
    session.mount(path, make_route_info(path))
    return messages, disconnect


def extract_count_from_ctx(session: Session, path: str) -> int:
    # Read latest VDOM by re-rendering from the RenderRoot and inspecting it
    ctx = session.render_contexts[path]
    with ctx:
        vdom: VDOM = ctx.root.render_vdom()
    vdom_dict = cast(dict, vdom)
    children = cast(list, (vdom_dict.get("children", []) or []))
    span = cast(dict, children[0])
    text_children = cast(list, span.get("children", [0]))
    text = text_children[0]
    return int(text)  # type: ignore[arg-type]


def test_two_sessions_two_routes_are_isolated():
    routes = make_routes()
    s1 = Session("s1", routes)
    s2 = Session("s2", routes)

    # Mount both routes on both sessions and keep listeners active
    msgs_s1_a, disc_s1_a = mount_with_listener(s1, "a")
    msgs_s1_b, disc_s1_b = mount_with_listener(s1, "b")
    msgs_s2_a, disc_s2_a = mount_with_listener(s2, "a")
    msgs_s2_b, disc_s2_b = mount_with_listener(s2, "b")

    # Initial counts are zero
    assert extract_count_from_ctx(s1, "a") == 0
    assert extract_count_from_ctx(s1, "b") == 0
    assert extract_count_from_ctx(s2, "a") == 0
    assert extract_count_from_ctx(s2, "b") == 0

    # Click a button in session 1 route a (button is second child, index 1)
    s1.execute_callback("a", "1.onClick", [])
    s1.flush()
    s2.flush()

    # s1:a should update, others should remain unchanged
    assert extract_count_from_ctx(s1, "a") == 1
    assert extract_count_from_ctx(s1, "b") == 0
    assert extract_count_from_ctx(s2, "a") == 0
    assert extract_count_from_ctx(s2, "b") == 0

    # Ensure s2 did not receive any update messages for either route
    assert len([m for m in msgs_s1_a if m["type"] == "vdom_update"]) == 1
    assert len([m for m in msgs_s1_b if m["type"] == "vdom_update"]) == 0
    assert len([m for m in msgs_s2_a if m["type"] == "vdom_update"]) == 0
    assert len([m for m in msgs_s2_b if m["type"] == "vdom_update"]) == 0

    # Click a button in session 2 route a (button is second child, index 1)
    s2.execute_callback("a", "1.onClick", [])
    s1.flush()
    s2.flush()

    # s2:a should update, others should remain unchanged
    assert extract_count_from_ctx(s1, "a") == 1
    assert extract_count_from_ctx(s1, "b") == 0
    assert extract_count_from_ctx(s2, "a") == 1
    assert extract_count_from_ctx(s2, "b") == 0

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
    route_a = Route("a", lambda: GlobalCounter("A"))
    route_b = Route("b", lambda: GlobalCounter("B"))
    return RouteTree([route_a, route_b])


def extract_global_count(session: Session, path: str) -> int:
    ctx = session.render_contexts[path]
    with ctx:
        vdom: VDOM = ctx.root.render_vdom()
    vdom_dict = cast(dict, vdom)
    children = cast(list, (vdom_dict.get("children", []) or []))
    span = cast(dict, children[0])
    text_children = cast(list, span.get("children", [0]))
    text = text_children[0]
    return int(text)  # type: ignore[arg-type]


def test_global_state_shared_within_session_and_isolated_across_sessions():
    routes = make_global_routes()
    s1 = Session("s1", routes)
    s2 = Session("s2", routes)

    # Mount both routes on both sessions
    msgs_s1_a, disc_s1_a = mount_with_listener(s1, "a")
    msgs_s1_b, disc_s1_b = mount_with_listener(s1, "b")
    msgs_s2_a, disc_s2_a = mount_with_listener(s2, "a")
    msgs_s2_b, disc_s2_b = mount_with_listener(s2, "b")

    # Initial counts are zero across both routes/sessions
    assert extract_global_count(s1, "a") == 0
    assert extract_global_count(s1, "b") == 0
    assert extract_global_count(s2, "a") == 0
    assert extract_global_count(s2, "b") == 0

    # Increment in s1 on route a
    s1.execute_callback("a", "1.onClick", [])
    s1.flush()
    s2.flush()

    # Within s1, both routes reflect the same per-session singleton (value == 1)
    assert extract_global_count(s1, "a") == 1
    assert extract_global_count(s1, "b") == 1
    # s2 remains unchanged
    assert extract_global_count(s2, "a") == 0
    assert extract_global_count(s2, "b") == 0

    # Route updates in s1 should include both routes
    assert len([m for m in msgs_s1_a if m["type"] == "vdom_update"]) >= 1
    assert len([m for m in msgs_s1_b if m["type"] == "vdom_update"]) >= 1
    # s2 should see no updates
    assert len([m for m in msgs_s2_a if m["type"] == "vdom_update"]) == 0
    assert len([m for m in msgs_s2_b if m["type"] == "vdom_update"]) == 0

    # Increment in s2 on route b
    s2.execute_callback("b", "1.onClick", [])
    s1.flush()
    s2.flush()

    # Within s2, both routes reflect value == 1; s1 unchanged
    assert extract_global_count(s1, "a") == 1
    assert extract_global_count(s1, "b") == 1
    assert extract_global_count(s2, "a") == 1
    assert extract_global_count(s2, "b") == 1

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

        def dispose(self):
            disposed.append("ok")
            super().dispose()

    accessor = ps.global_state(Disposable)

    routes = RouteTree([Route("a", lambda: ps.div()[ps.span()[str(accessor().count)]])])
    s = Session("s1", routes)
    _msgs, disc = mount_with_listener(s, "a")
    # Ensure instance is created by rendering
    assert extract_count_from_ctx(s, "a") == 0

    # Close session -> should dispose the global singleton instance
    disc()
    s.close()
    assert disposed == ["ok"]


def test_dummy_placeholder_to_keep_line_numbers_stable():
    # Placeholder after revert; keep file stable
    assert True
