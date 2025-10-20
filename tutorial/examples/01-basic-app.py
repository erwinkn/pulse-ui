"examples/01-basic-app.py"

from pathlib import Path
import pulse as ps


@ps.component
def Welcome():
    return ps.div(
        className="min-h-screen flex items-center justify-center flex-col bg-gray-100"
    )[
        ps.h1("Welcome to Pulse!", className="text-4xl font-bold text-blue-600 mb-4"),
        ps.p(
            "You've created your first Pulse application!",
            className="text-lg text-gray-700",
        ),
    ]


app = ps.App(
    routes=[ps.Route("/", Welcome)],
)
