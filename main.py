import pulse as ps

# Import modules with decorated routes or any other code you need here

app = ps.App(
    routes=[
        *ps.decorated_routes(),
        ps.Route("/manual-route", manual_route_fn, components=[]),
    ]
)
