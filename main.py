import asyncio
from datetime import datetime
from pathlib import Path
import time
import pulse as ps
from pulse.codegen import CodegenConfig
from pulse.middleware import Ok, Redirect, NotFound, Deny
from typing import Optional


# State Management
# ----------------
# A state class for the counter, demonstrating state variables, methods,
# computed properties, and effects.
class CounterState(ps.State):
    count: int = 0
    count2: int = 0
    ticking = False

    def __init__(self, name: str):
        self._name = name

    def increment(self):
        self.count += 1

    async def increment_with_delay(self):
        await asyncio.sleep(1)
        self.count += 1
        self.count += 1
        await asyncio.sleep(1)
        self.count += 1
        self.count += 1

    async def start_ticking(self):
        self.ticking = True
        while True:
            if not self.ticking:
                break
            self.count += 1
            await asyncio.sleep(1)

    def stop_ticking(self):
        self.ticking = False

    def decrement(self):
        self.count -= 1

    @ps.computed
    def double_count(self) -> int:
        """A computed property that doubles the count."""
        return self.count * 2

    @ps.effect
    def on_count_change(self):
        """An effect that runs whenever the count changes."""
        print(
            f"{self._name}: Count is now {self.count}. Double is {self.double_count}."
        )


# A state class for the layout, demonstrating persistent state across routes.
class LayoutState(ps.State):
    """A state class for the layout, demonstrating persistent state across routes."""

    shared_count: int = 0

    def increment(self):
        self.shared_count += 1


# Nested Components Demo State
# ----------------------------
class LeafState(ps.State):
    count: int = 0

    def __init__(self, label: str):
        self._label = label

    def inc(self):
        self.count += 1

    @ps.effect
    def on_change(self):
        # Demonstrate a state-level effect; safe to be defined once per instance
        _ = self.count  # read to establish dependency


class NestedDemoState(ps.State):
    swapped: bool = False

    def toggle_swap(self):
        print("--- SWAP ---")
        self.swapped = not self.swapped


# Components & Pages
# ------------------
# Components are the building blocks of a Pulse UI. They can have their own
# state and render other components.


@ps.component
def home():
    """A simple and welcoming home page."""
    sess = ps.session_context()
    content = [
        ps.h1("Welcome to Pulse UI!", className="text-4xl font-bold mb-4"),
        ps.p(
            "This is a demonstration of a web application built with Python and Pulse.",
            className="text-lg text-gray-700",
        ),
    ]
    # Avoid prerender flash of None by only rendering once we have values
    if sess.get("connected_at") or sess.get("ip") or sess.get("user_agent"):
        content.append(
            ps.div(
                ps.h3("Session Context", className="text-2xl font-semibold mb-2"),
                ps.ul(
                    ps.li(f"connected_at: {sess.get('connected_at') or ''}"),
                    ps.li(f"ip: {sess.get('ip') or ''}"),
                    ps.li(f"user_agent: {sess.get('user_agent') or ''}"),
                    className="list-disc list-inside text-left mx-auto max-w-md",
                ),
                className="mt-6 p-4 bg-gray-50 rounded border",
            )
        )
    return ps.div(*content, className="text-center")


@ps.component
def about():
    """An about page highlighting key features of Pulse."""
    features = [
        "Define UI components entirely in Python.",
        "Handle frontend events with Python functions.",
        "Manage state with reactive classes.",
        "Create layouts and nested routes effortlessly.",
    ]
    return ps.div(
        ps.h1("About Pulse", className="text-3xl font-bold mb-6"),
        ps.p(
            "Pulse bridges the gap between Python and modern web development, enabling you to build interactive UIs with ease.",
            className="mb-6",
        ),
        ps.ul(
            *[
                ps.li(feature, className="mb-2 p-2 bg-gray-100 rounded")
                for feature in features
            ],
            className="list-disc list-inside",
        ),
    )


def setup_counter(count: int):
    @ps.effect
    def log_count():
        print(f"Logging count from setup: {count}")


@ps.component
def Leaf(label: str):
    # setup: called once per component instance; captures mount-only effect
    def _init(lbl: str):
        @ps.effect
        def on_mount():
            print(f"[Leaf mount] {lbl}")

        return {"label": lbl}

    meta = ps.setup(_init, label)

    # states: called once per component instance
    state = ps.states(LeafState(meta["label"]))
    print(f"Rendering leaf {label} with count {state.count}")

    # effects: register a mount-only effect for the component instance
    ps.effects(lambda: print(f"[Leaf effects] ready: {meta['label']}"))

    return ps.div(
        ps.div(
            ps.span(f"{label}: ", className="font-semibold mr-2"),
            ps.button("+", onClick=state.inc, className="btn-primary mr-2"),
            ps.span(f"{state.count}", className="font-mono"),
            className="flex items-center",
        ),
        className="p-2 border rounded",
    )


@ps.component
def Row(use_keys: bool, swapped: bool):
    if not swapped:
        return ps.div(className="grid grid-cols-2 gap-4")[
            Leaf(label="Left", key="left" if use_keys else None),
            Leaf(label="Right", key="right" if use_keys else None),
        ]
    else:
        return ps.div(className="grid grid-cols-2 gap-4")[
            Leaf(label="Right", key="right" if use_keys else None),
            Leaf(label="Left", key="left" if use_keys else None),
        ]


@ps.component
def components_demo():
    state = ps.states(NestedDemoState)

    return ps.div(
        ps.h1("Nested Components & Keys", className="text-2xl font-bold mb-4"),
        ps.div(
            ps.button(
                "Swap children",
                onClick=state.toggle_swap,
                className="btn-secondary",
            ),
            ps.span(
                f" swapped={state.swapped}",
                className="ml-3 text-sm text-gray-600",
            ),
            className="mb-4",
        ),
        ps.div(
            ps.h2("Unkeyed children", className="text-xl font-semibold mb-2"),
            Row(use_keys=False, swapped=state.swapped),
            className="mb-6 p-4 rounded bg-white shadow",
        ),
        ps.div(
            ps.h2("Keyed children", className="text-xl font-semibold mb-2"),
            Row(use_keys=True, swapped=state.swapped),
            ps.p(
                "With keys, each child's state sticks with its key across reordering.",
                className="text-sm text-gray-600 mt-2",
            ),
            className="p-4 rounded bg-white shadow",
        ),
    )


@ps.component
def counter():
    """An interactive counter page demonstrating state management."""
    state1, state2 = ps.states(CounterState("Counter 1"), CounterState("Counter2"))
    route_info = ps.route_info()

    return ps.div(
        ps.h1("Interactive Counter", className="text-3xl font-bold mb-4"),
        ps.div(
            ps.button("Decrement", onClick=state1.decrement, className="btn-primary"),
            ps.span(f"{state1.count}", className="text-2xl font-mono"),
            ps.button("Increment", onClick=state1.increment, className="btn-primary"),
            ps.button(
                "Batch increment with delay",
                onClick=state1.increment_with_delay,
                className="btn-primary",
            ),
            className="flex items-center justify-center space-x-4",
        ),
        ps.div(className="flex items-center justify-center space-x-4")[
            ps.button(
                "Start ticking", onClick=state1.start_ticking, className="btn-primary"
            ),
            ps.button(
                "Stop ticking", onClick=state1.stop_ticking, className="btn-primary"
            ),
        ],
        ps.p(f"The doubled count is: {state1.double_count}", className="text-lg mb-4"),
        ps.h1("Interactive Counter 2", className="text-3xl font-bold mb-4"),
        ps.div(
            ps.button("Decrement", onClick=state2.decrement, className="btn-primary"),
            ps.span(f"{state2.count}", className="mx-4 text-2xl font-mono"),
            ps.button("Increment", onClick=state2.increment, className="btn-primary"),
            className="flex items-center justify-center mb-4",
        ),
        ps.p(f"The doubled count is: {state2.double_count}", className="text-lg mb-4"),
        ps.p(
            "Check your server logs for messages from the @ps.effect.",
            className="text-sm text-gray-500 mb-6",
        ),
        ps.div(
            ps.button(
                "Show Nested Route",
                onClick=lambda: ps.navigate("/counter/details"),
                className="link",
            )
            if route_info.pathname == "/counter"
            else ps.Link("Hide Nested Route", to="/counter", className="link"),
            className="text-center",
        ),
        ps.div(
            ps.Outlet(),
            className="mt-6 p-4 border-t border-gray-200",
        ),
    )


@ps.component
def counter_details():
    """A nested child component for the counter page."""
    return ps.div(
        ps.h2("Counter Details", className="text-2xl font-bold mb-2"),
        ps.p(
            "This is a nested route. It has its own view but can share state if needed."
        ),
        ps.p(
            ps.Link("Hide Details", to="/counter", className="link mt-2 inline-block")
        ),
        className="bg-blue-50 p-4 rounded-lg",
    )


class QueryDemoState(ps.State):
    user_id: int = 1
    calls: int = 0

    @ps.query
    async def user(self) -> dict:
        self.calls += 1
        # Simulate async work
        await asyncio.sleep(1)
        return {"id": self.user_id, "name": f"User {self.user_id}"}

    @user.key
    def _user_key(self):
        return ("user", self.user_id)


@ps.component
def query_demo():
    state = ps.states(QueryDemoState)
    q = state.user

    def prev():
        state.user_id = max(1, state.user_id - 1)

    def next_():
        state.user_id = state.user_id + 1

    def refetch():
        q.refetch()

    return ps.div(
        ps.h2("Query Demo", className="text-2xl font-bold mb-4"),
        ps.p(f"User ID: {state.user_id}"),
        ps.p(f"Fetch calls: {state.calls}"),
        ps.p("Loading..." if q.is_loading else f"Data: {q.data}", className="mb-4"),
        ps.div(
            ps.button("Prev", onClick=prev, className="btn-secondary mr-2"),
            ps.button("Next", onClick=next_, className="btn-secondary mr-2"),
            ps.button("Refetch", onClick=refetch, className="btn-primary"),
        ),
        className="p-4",
    )


@ps.component
def dynamic_route():
    route = ps.route_info()
    return ps.div(
        ps.h2("Dynamic Route Info", className="text-xl font-bold mb-2"),
        ps.ul(
            ps.li(f"Pathname: {route.pathname}"),
            ps.li(f"Hash: {route.hash}"),
            ps.li(f"Query: {route.query}"),
            ps.li(f"Query Params: {route.queryParams}"),
            ps.li(f"Path Params: {route.pathParams}"),
            ps.li(f"Catchall: {route.catchall}"),
            className="list-disc ml-6",
        ),
        className="bg-yellow-50 p-4 rounded-lg",
    )


@ps.react_component(
    tag="CustomDatePicker",
    import_="~/components/date-picker",
    is_default=True,
    lazy=True,
)
def DatePicker(
    *children: ps.Element,
    key: Optional[str] = None,
    value: Optional[datetime] = None,
    onChange: Optional[ps.EventHandler[datetime | None]] = None,
    placeholder: str = "Select a date",
    className: str = "",
    showTimeSelect: bool = False,
) -> ps.Element:
    return None  # signature-only; parsed for prop spec


class DatePickerState(ps.State):
    value: Optional[datetime] = None

    def set_value(self, v: datetime | None):
        print(f"Received value: {v} (type: {type(v)})")
        self.value = v


@ps.component
def datepicker_demo():
    state = ps.states(DatePickerState)

    return ps.div(
        ps.h2("Date Picker", className="text-2xl font-bold mb-4"),
        ps.p("Pick a date and time (ISO string will show below).", className="mb-2"),
        DatePicker(
            value=state.value,
            onChange=state.set_value,
            showTimeSelect=True,
            className="max-w-sm",
        ),
        ps.p(f"Selected: {state.value or '-'}", className="mt-4 font-mono"),
        className="p-4",
    )


@ps.component
def app_layout():
    """The main layout for the application, including navigation and a persistent counter."""
    state = ps.states(LayoutState)

    return ps.div(
        ps.header(
            ps.div(
                ps.h1("Pulse Demo", className="text-2xl font-bold"),
                ps.div(
                    ps.span(f"Shared Counter: {state.shared_count}", className="mr-4"),
                    ps.button(
                        "Increment Shared",
                        onClick=state.increment,
                        className="btn-secondary",
                    ),
                    className="flex items-center",
                ),
                className="flex justify-between items-center p-4 bg-gray-800 text-white",
            ),
            ps.nav(
                ps.Link("Home", to="/", className="nav-link"),
                ps.Link("Counter", to="/counter", className="nav-link"),
                ps.Link("About", to="/about", className="nav-link"),
                ps.Link("Components", to="/components", className="nav-link"),
                ps.Link("Date Picker", to="/datepicker", className="nav-link"),
                ps.Link(
                    "Dynamic",
                    to="/dynamic/example/optional/a/b/c?q1=x&q2=y",
                    className="nav-link",
                ),
                ps.Link("Query", to="/query", className="nav-link"),
                className="flex justify-center space-x-4 p-4 bg-gray-700 text-white rounded-b-lg",
            ),
            className="mb-8",
        ),
        ps.main(ps.Outlet(), className="container mx-auto px-4"),
        className="min-h-screen bg-gray-100 text-gray-800",
    )


# Routing
# -------
# Define the application's routes. A layout route wraps all other routes
# to provide a consistent navigation experience.
app = ps.App(
    routes=[
        ps.Layout(
            app_layout,
            children=[
                ps.Route("/", home),
                ps.Route("/about", about),
                ps.Route(
                    "/counter",
                    counter,
                    children=[
                        ps.Route("details", counter_details),
                    ],
                ),
                ps.Route("/components", components_demo),
                ps.Route("/datepicker", datepicker_demo),
                ps.Route("/query", query_demo),
                ps.Route("/dynamic/:route_id/:optional_segment?/*", dynamic_route),
            ],
        )
    ],
    middleware=None,
    codegen=CodegenConfig(web_dir=Path(__file__).parent / "pulse-demo"),
)


# --- Demo Middleware ---------------------------------------------------------


class LoggingMiddleware(ps.PulseMiddleware):
    def prerender(self, *, path, route_info, request, context, next):
        # before
        print(f"[MW prerender] path={path} host={request.headers.get('host')}")
        # Seed same keys as connect to avoid prerender flash
        context["user_agent"] = request.headers.get("user-agent")
        context["ip"] = request.headers.get("x-forwarded-for") or (
            request.client[0] if request.client else None
        )
        context["connected_at"] = context.get("connected_at") or int(time.time())
        res = next()
        # after
        if isinstance(res, Ok):
            kind = "ok"
        elif isinstance(res, Redirect):
            kind = f"redirect:{res.path}"
        elif isinstance(res, NotFound):
            kind = "not_found"
        else:
            kind = type(res).__name__
        print(f"[MW prerender:after] kind={kind}")
        return res

    def connect(self, *, request, ctx, next):
        # Add some context visible in components
        ua = request.headers.get("user-agent")
        ip = request.client[0] if request.client else None
        ctx["user_agent"] = ua
        ctx["ip"] = ip
        ctx["connected_at"] = int(time.time())
        print(f"[MW connect] ip={ip} ua={(ua or '')[:40]}")
        return next()

    def message(self, *, ctx, data, next):
        # Light logging of message types
        try:
            msg_type = data.get("type")
        except Exception:
            msg_type = "<unknown>"
        # Do not spam logs for vdom churn; only mount/navigate/callback
        if msg_type in {"mount", "navigate", "callback", "unmount"}:
            print(f"[MW message] type={msg_type}")
        res = next()
        if isinstance(res, Ok):
            result = "ok"
        elif isinstance(res, Deny):
            result = "deny"
        else:
            result = type(res).__name__
        print(f"[MW message:after] type={msg_type} result={result}")
        return res


# Attach middleware (keep config separate from routes for clarity)
# app._middleware = LoggingMiddleware()
