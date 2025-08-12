"""
Integration-ish tests for session isolation.

We spin up a minimal route tree with two routes and create two sessions.
Each session mounts both routes and mutates state via callbacks. We assert
that updates from one session do not leak into the other.
"""

from typing import cast

import pulse as ps
from pulse.messages import RouteInfo, ServerMessage
from pulse.routing import Route, RouteTree
from pulse.session import Session
from pulse.reactive import flush_effects
from pulse.vdom import Node


class Counter(ps.State):
    count: int = 0

    @ps.effect
    def on_change(self):
        _ = self.count  # track


def make_counter_component(session_name: str, key_prefix: str):
    state = ps.states(Counter)

    def inc():
        state.count = state.count + 1

    # Render current count + a callback
    return ps.div(key=f"{key_prefix}:{session_name}")[
        ps.span(id=f"count-{session_name}")[str(state.count)],
        ps.button(onClick=inc)["inc"],
    ]


def make_routes() -> RouteTree:
    route_a = Route("a", lambda: make_counter_component("A", "route-a"))
    route_b = Route("b", lambda: make_counter_component("B", "route-b"))
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
    messages: list = []

    def on_message(msg: ServerMessage):
        if msg["path"] != path:
            return
        messages.append(msg)

    disconnect = session.connect(on_message)
    session.mount(path, make_route_info(path), current_vdom=None)
    flush_effects()
    return messages, disconnect


def extract_count_from_ctx(session: Session, path: str) -> int:
    # Read latest VDOM by re-rendering the server node and inspecting it
    ctx = session.render_contexts[path]
    node = ctx.node
    assert isinstance(node, Node)
    vdom, _ = node.render()
    children = cast(list, (vdom.get("children", []) or []))
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
    flush_effects()

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
    flush_effects()

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
