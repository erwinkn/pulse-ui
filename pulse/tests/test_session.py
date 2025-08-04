"""
Tests for the Session class.
"""

from unittest.mock import MagicMock, call
import pytest
import pulse as ps
from pulse.session import Session, ActiveRoute
from pulse.diff import VDOM
from pulse.vdom import VDOMNode, Node


class MockVDOMNode(Node):
    def render(self):
        # A simplified render that extracts callbacks like the real one
        callbacks = {}
        clean_props = {}
        for k, v in (self.props or {}).items():
            if callable(v):
                callbacks[k] = v
            else:
                clean_props[k] = v

        children = []
        for child in self.children or []:
            if isinstance(child, Node):
                child_vdom, child_callbacks = child.render()
                children.append(child_vdom)
                callbacks.update(child_callbacks)
            else:
                children.append(child)

        vdom: VDOMNode = {"tag": self.tag, "props": clean_props, "children": children}
        return vdom, callbacks


class TestSession:
    def setup_method(self):
        self.routes = MagicMock()
        self.session = Session("test_session", self.routes)

    def test_navigate_initial_render(self):
        path = "/test"

        mock_render_fn = MagicMock()
        mock_node = MockVDOMNode("div")
        mock_render_fn.return_value = mock_node
        self.routes.find.return_value = ps.routing.Route(
            path=path, render_fn=mock_render_fn
        )

        message_listener = MagicMock()
        self.session.connect(message_listener)

        self.session.navigate(path)

        assert path in self.session.active_routes
        mock_render_fn.assert_called_once()
        message_listener.assert_called_once()

        sent_message = message_listener.call_args[0][0]
        assert sent_message["type"] == "vdom_init"
        assert sent_message["route"] == path
        assert "vdom" in sent_message

    def test_rerender_on_state_change(self):
        path = "/test"

        class MyState(ps.State):
            count: int = 0

        state = MyState()

        def render_fn():
            return MockVDOMNode("p", children=[str(state.count)])

        self.routes.find.return_value = ps.routing.Route(path=path, render_fn=render_fn)

        message_listener = MagicMock()
        self.session.connect(message_listener)

        self.session.navigate(path)

        # Initial render sends vdom_init
        message_listener.assert_called_once()
        first_message = message_listener.call_args[0][0]
        assert first_message["type"] == "vdom_init"

        # Update state and trigger rerender
        state.count = 1

        # Should have been called a second time
        assert message_listener.call_count == 2
        second_message = message_listener.call_args_list[1][0][0]
        assert second_message["type"] == "vdom_update"
        assert "ops" in second_message

    def test_init_hook(self):
        path = "/test"
        setup_fn = MagicMock(return_value={"count": ps.Signal(0)})

        def render_fn():
            state = ps.init(setup_fn)
            return MockVDOMNode("p", children=[str(state["count"]())])

        self.routes.find.return_value = ps.routing.Route(path=path, render_fn=render_fn)

        self.session.navigate(path)

        # setup_fn should be called once on first render
        setup_fn.assert_called_once()

        # Trigger a re-render
        active_route = self.session.active_routes[path]
        state = active_route.reactive_state.setup.value
        state["count"].write(1)

        # setup_fn should still only have been called once
        setup_fn.assert_called_once()

    def test_init_called_twice_raises_error(self):
        path = "/test"

        def render_fn():
            ps.init(lambda: {})
            ps.init(lambda: {})  # Call it again
            return MockVDOMNode("div")

        self.routes.find.return_value = ps.routing.Route(path=path, render_fn=render_fn)

        with pytest.raises(RuntimeError):
            self.session.navigate(path)

    def test_execute_callback(self):
        path = "/test"
        mock_callback = MagicMock()

        def render_fn():
            return MockVDOMNode("div", props={"onClick": mock_callback})

        self.routes.find.return_value = ps.routing.Route(path=path, render_fn=render_fn)

        self.session.navigate(path)

        self.session.execute_callback(path, "onClick", (1, "hello"))

        mock_callback.assert_called_once_with(1, "hello")

    def test_leave_route(self):
        path = "/test"
        self.routes.find.return_value = ps.routing.Route(
            path=path, render_fn=lambda: MockVDOMNode("div")
        )

        self.session.navigate(path)
        active_route = self.session.active_routes[path]
        active_route.effect.dispose = MagicMock()

        self.session.leave(path)

        active_route.effect.dispose.assert_called_once()

    def test_session_close(self):
        paths = ["/a", "/b"]
        for path in paths:
            self.routes.find.return_value = ps.routing.Route(
                path=path, render_fn=lambda: MockVDOMNode("div")
            )
            self.session.navigate(path)

        # Mock dispose on each effect
        for route in self.session.active_routes.values():
            route.effect.dispose = MagicMock()

        dispose_mocks = [
            route.effect.dispose for route in self.session.active_routes.values()
        ]

        self.session.close()

        for mock in dispose_mocks:
            mock.assert_called_once()
        assert len(self.session.active_routes) == 0
