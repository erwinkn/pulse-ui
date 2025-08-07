import pulse as ps


# State Management
# ----------------
# A state class for the counter, demonstrating state variables, methods,
# computed properties, and effects.
class CounterState(ps.State):
    count: int = 0
    count2: int = 0

    def __init__(self, name: str):
        self.name = name

    def increment(self):
        self.count += 1

    def decrement(self):
        self.count -= 1

    @ps.computed
    def double_count(self) -> int:
        """A computed property that doubles the count."""
        return self.count * 2

    @ps.effect
    def on_count_change(self):
        """An effect that runs whenever the count changes."""
        print(f"{self.name}: Count is now {self.count}. Double is {self.double_count}.")


# A state class for the layout, demonstrating persistent state across routes.
class LayoutState(ps.State):
    """A state class for the layout, demonstrating persistent state across routes."""

    shared_count: int = 0

    def increment(self):
        self.shared_count += 1


# Components & Pages
# ------------------
# Components are the building blocks of a Pulse UI. They can have their own
# state and render other components.


@ps.component
def home():
    """A simple and welcoming home page."""
    return ps.div(
        ps.h1("Welcome to Pulse UI!", className="text-4xl font-bold mb-4"),
        ps.p(
            "This is a demonstration of a web application built with Python and Pulse.",
            className="text-lg text-gray-700",
        ),
        className="text-center",
    )


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
        ps.ul(className="list-disc list-inside")[
            *[
                ps.li(feature, className="mb-2 p-2 bg-gray-100 rounded")
                for feature in features
            ],
        ],
    )


def setup_counter(count: int):
    @ps.effect
    def log_count():
        print(f"Logging count from setup: {count}")


@ps.component
def counter():
    """An interactive counter page demonstrating state management."""
    state1, state2 = ps.states(CounterState("Counter 1"), CounterState("Counter2"))

    return ps.div(
        ps.h1("Interactive Counter", className="text-3xl font-bold mb-4"),
        ps.div(
            ps.button("Decrement", onClick=state1.decrement, className="btn-primary"),
            ps.span(f"{state1.count}", className="mx-4 text-2xl font-mono"),
            ps.button("Increment", onClick=state1.increment, className="btn-primary"),
            className="flex items-center justify-center mb-4",
        ),
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
            ps.Link("Show Nested Route", to="/counter/details", className="link"),
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


@ps.component
def dynamic_route():
    router = ps.router()
    return ps.div(
        ps.h2("Dynamic Route Info", className="text-xl font-bold mb-2"),
        ps.ul(
            ps.li(f"Pathname: {router.pathname}"),
            ps.li(f"Hash: {router.hash}"),
            ps.li(f"Query: {router.query}"),
            ps.li(f"Query Params: {router.queryParams}"),
            ps.li(f"Path Params: {router.pathParams}"),
            ps.li(f"Catchall: {router.catchall}"),
            className="list-disc ml-6",
        ),
        className="bg-yellow-50 p-4 rounded-lg",
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
                ps.Link("Dynamic", to="/dynamic", className="nav-link"),
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
                ps.Route("/dynamic/:route_id/:optional_segment?/*", dynamic_route),
            ],
        )
    ]
)
