import pulse as ps


@ps.route("/")
def home():
    """Home page with a greeting and interactive button."""

    def handle_click():
        print("🎉 Button clicked from Python!")

    return ps.div(
        ps.h1("Welcome to Pulse UI!"),
        ps.p("This is a Python-powered web application."),
        ps.button("Click me!", onClick=handle_click),
        ps.hr(),
        ps.p("Check the server logs to see the button click messages."),
    )



@ps.route("/about")
def about():
    """About page with information."""
    return ps.div(
        ps.h1("About Pulse UI"),
        ps.p("Pulse UI bridges Python and React, allowing you to:"),
        ps.ul(
            ps.li("Define UI components in Python", key="feature-1"),
            ps.li("Handle events with Python functions", key="feature-2"),
            ps.li("Generate TypeScript automatically", key="feature-3"),
            ps.li("Build reactive web applications", key="feature-4"),
        ),
        ps.p(ps.a("← Back to Home", href="/")),
    )


class CounterState(ps.State):
    count: int = 4

    def increment(self):
        print("Counter incremented!")
        self.count += 1


@ps.route("/counter")
def counter():
    """Interactive counter page."""
    # Both state methods and arbitrary functions work as event handlers

    def decrement():
        print("Counter decremented!")
        state.count -= 1

    state = ps.init(lambda: CounterState())

    return ps.div(
        ps.h1("Counter Example"),
        ps.div(
            ps.button("-", onClick=decrement),
            ps.span(
                f" Counter: {state.count} ",
                style={"margin": "0 20px", "fontSize": "18px"},
            ),
            ps.button("+", onClick=state.increment),
        ),
        ps.p(
            "Note: This is a simple demo. State management would require additional implementation."
        ),
        ps.p(ps.Link("← Back to Home", to="/")),
    )


# Create the Pulse app
app = ps.App(routes=[*ps.decorated_routes()])
