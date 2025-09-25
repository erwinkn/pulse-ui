from pathlib import Path
import pulse as ps


@ps.component
def Home():
    return ps.div(
        ps.h2(f"Client address: {ps.client_address()}"),
        ps.h2(f"Server address: {ps.server_address()}"),
    )


app = ps.App(
    [ps.Route("/", Home)],
)
