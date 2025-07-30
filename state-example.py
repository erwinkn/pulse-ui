import pulse as ps

class CounterState(ps.State):
    count: int = 0


@ps.route("/counter")
def counter():
    def init():
        return CounterState()

    state = ps.init(init) # this always returns the same instance of CounterState across rerenders
    # 
    return ps.div(
        ps.h1("Counter Example"),
        ps.div(
            # Event handlers will be implemented once we integrate with the client
            ps.button("-"),
            ps.span(f" Counter: {state.count}", style={"margin": "0 20px", "fontSize": "18px"}),
            ps.button("+"),
        ),
        ps.p(
            "Note: This is a simple demo. State management would require additional implementation."
        ),
        ps.p(ps.a("← Back to Home", href="/")),
    )

if __name__ == "__main__":
    app = ps.App(routes=[*ps.decorated_routes()])

    def on_update(update):
        # use this callback to log or test the updates
        print("VDOM update:", update)

    active = app.render("/counter", on_update=on_update)
    # This property stores the result of the `init` function. In this case, it's an instance of CounterState
    state = active.state 
    # This property stores the current vdom of the route
    vdom = active.vdom 

    # This should be caught by the property setter, trigger a route rerender, a VDOM
    # diff, and a call to on_update with the updates obtained from the VDOM diff.
    state.count = 2

