import asyncio
from datetime import datetime
import time
from pathlib import Path
from typing import Callable, Optional

import pulse as ps
from pulse.codegen import CodegenConfig


# Weather Board Demo
# ------------------
# A compact, end-to-end Pulse app that we can build up step-by-step in a guide.
# It demonstrates:
# - Creating an App and adding routes
# - Generating HTML from components
# - Local component state with ps.State and ps.states()
# - Event handlers (sync and async) and automatic batching of synchronous writes
# - Queries with keys and loading states
# - Effects that react to state changes
# - Layouts and a dynamic route (per-city details)


# --- Core domain helpers (pure Python) ---------------------------------------


def c_to_f(celsius: float) -> float:
    return round((celsius * 9.0) / 5.0 + 32.0, 1)


def fake_weather_backend(city: str) -> dict:
    """Pretend to hit an API and return some stable, fake data.

    We seed values by city name hash to get deterministic temperatures.
    """
    base = (sum(ord(ch) for ch in city) % 15) + 10  # 10..24
    temp_c = float(base)
    return {
        "city": city,
        "temp_c": temp_c,
        "temp_f": c_to_f(temp_c),
        "conditions": "Sunny" if base % 2 == 0 else "Cloudy",
        "updated_at": int(time.time()),
    }


# --- Shared layout state -----------------------------------------------------


class LayoutState(ps.State):
    """State that lives at the layout level (persists across route changes).

    This demonstrates a layout-local state that can influence UI in the header.
    (Hooks like ps.states() are unique per component; children don't implicitly
    share this state instance unless you thread values through or use context.)
    """

    units: str = "C"  # "C" or "F"

    def toggle_units(self):
        u = "F" if self.units == "C" else "C"
        print(f"Setting unit to {u}")
        self.units = u


layout_state = ps.global_state(LayoutState)


# --- Board state (home page) -------------------------------------------------


class BoardState(ps.State):
    """State for the home route: tracks a small list of cities and UI stats."""

    cities: list[str]
    last_added: Optional[str] = None
    last_refreshed_at: Optional[datetime] = None

    def __init__(self):
        self.cities = ["San Francisco", "New York"]

    @ps.computed
    def count(self) -> int:
        return len(self.cities)

    def add_city(self, city: str):
        # Multiple synchronous writes here are automatically batched
        # into a single render.
        if city not in self.cities:
            self.cities = [*self.cities, city]
            self.last_added = city

    def remove_city(self, city: str):
        self.cities = [c for c in self.cities if c != city]

    async def refresh_all(self):
        self.last_refreshed_at = datetime.now()

    @ps.effect
    def on_city_list_change(self):
        # Effect: runs when its dependencies are read; establish dependency by
        # reading self.cities and self.count.
        print(f"Cities ({self.count}): {', '.join(self.cities)}")


# --- Per-city state and query (used in cards and details page) ---------------


class CityState(ps.State):
    """State instance bound to a specific city; embeds a query."""

    calls: int = 0
    city: str

    def __init__(self, city: str, board_state: Optional[BoardState] = None):
        self.city = city
        self._board_state = board_state

    @ps.query
    async def weather(self) -> dict:
        # Simulate latency, then return data from our fake backend.
        self.calls += 1
        await asyncio.sleep(0.4)
        return fake_weather_backend(self.city)

    @weather.key
    def _weather_key(self):
        # Key the query by city so caches work independently per city.
        return (
            "weather",
            self.city,
            self._board_state.last_refreshed_at if self._board_state else None,
        )


# --- Components --------------------------------------------------------------


@ps.component
def CityCard(board_state: BoardState, city: str, onRemove: Callable[[str], None]):
    """A small reusable component for a city's mini weather card.

    Demonstrates:
    - Component-local state instance with ps.states(CityState(...))
    - A query for weather data and a loading state
    - A link to a dynamic route for details
    """

    state = ps.states(CityState(city, board_state))
    q = state.weather

    if q.is_loading:
        body = ps.div("Loading...", className="text-gray-500 italic")
    else:
        data = q.data or {}
        units = layout_state().units
        temp = (
            f"{data.get('temp_c', '-')}°C"
            if units == "C"
            else f"{data.get('temp_f', '-')}°F"
        )
        body = ps.div(
            ps.p(f"{data.get('conditions', '-')}", className="text-sm text-gray-600"),
            ps.p(temp, className="text-lg font-mono"),
        )

    return ps.div(
        ps.h3(city, className="font-semibold text-lg"),
        body,
        ps.div(
            ps.Link("Details", to=f"/city/{city}", className="link mr-2"),
            ps.button(
                "Remove", onClick=lambda: onRemove(city), className="btn-secondary"
            ),
            className="mt-2",
        ),
        className="p-3 border rounded bg-white shadow-sm",
    )


@ps.component
def home():
    """Home route: manage a small list of cities and render cards."""

    board = ps.states(BoardState)

    candidates = ["San Francisco", "New York", "London", "Tokyo", "Berlin"]

    return ps.div(
        ps.h1("City Weather Board", className="text-2xl font-bold mb-4"),
        ps.p(
            "Click a city to add it. Synchronous state writes are batched.",
            className="text-sm text-gray-600 mb-2",
        ),
        ps.p(
            (
                f"Last refreshed: {board.last_refreshed_at}"
                if board.last_refreshed_at
                else ""
            ),
            className="text-xs text-gray-500 mb-1",
        ),
        ps.div(
            # Gotcha: doing this with a regular list comprehension means the
            # onClick always gets the last value of `name`.
            *ps.For(
                candidates,
                lambda name: ps.fragment(
                    ps.button(
                        name,
                        onClick=lambda: board.add_city(name),
                        className="btn-primary mr-2 mb-2",
                    )
                ),
            ),
            className="mb-4",
        ),
        ps.div(ps.span(f"Cities: {board.count}", className="mr-3"), className="mb-2"),
        ps.div(
            *[
                CityCard(city=c, board_state=board, onRemove=board.remove_city, key=c)
                for c in board.cities
            ],
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4",
        ),
        ps.div(
            ps.button(
                "Refresh All (async)",
                onClick=board.refresh_all,
                className="btn-secondary mt-4",
            ),
        ),
        className="p-4",
    )


class CityPageState(ps.State):
    """Local state for the city details page.

    Shows how to combine a state with a query, as well as extra UI counters.
    """

    async_clicks: int = 0
    tab: str = "overview"
    city: str

    def __init__(self, city: str):
        self.city = city

    @ps.computed
    def title(self) -> str:
        return f"Weather: {self.city}"

    async def burst(self):
        # Async event handler doing multiple state writes with awaits in-between.
        await asyncio.sleep(1)
        self.async_clicks += 1
        self.async_clicks += 1
        await asyncio.sleep(1)
        self.async_clicks += 1
        self.async_clicks += 1


@ps.component
def city_details():
    """Dynamic route page: `/city/:name`.

    Demonstrates route params, a per-city query, computed props, and async events.
    """

    route = ps.route_info()
    city_name = route.pathParams.get("name", "")

    # Setup ensures a stable capture of the city name for this component instance
    meta = ps.setup(lambda n: {"city": n}, city_name)
    # IMPORTANT: Only call ps.states() once per component. Initialize all needed
    # state instances in a single call and destructure.
    page_state, city_state = ps.states(
        CityPageState(meta["city"]),
        CityState(meta["city"]),
    )
    q = city_state.weather
    units = layout_state().units

    return ps.div(
        ps.h2(page_state.title, className="text-xl font-bold mb-2"),
        ps.p(ps.Link("Back", to="/", className="link"), className="mb-2"),
        ps.div(
            ps.button(
                "Overview",
                onClick=lambda: setattr(page_state, "tab", "overview"),
                className="btn-secondary mr-2",
            ),
            ps.button(
                "Trends",
                onClick=lambda: setattr(page_state, "tab", "trends"),
                className="btn-secondary",
            ),
            className="mb-3",
        ),
        ps.p(
            f"Tab: {page_state.tab} | Async clicks: {page_state.async_clicks}",
            className="text-sm text-gray-600 mb-3",
        ),
        (
            ps.div("Loading weather...", className="italic text-gray-500")
            if q.is_loading
            else (
                ps.div(
                    ps.p(
                        f"Conditions: {(q.data or {}).get('conditions', '-')}",
                        className="mb-1",
                    ),
                    ps.p(
                        (
                            f"Temperature: {(q.data or {}).get('temp_c', '-')}°C"
                            if units == "C"
                            else f"Temperature: {(q.data or {}).get('temp_f', '-')}°F"
                        ),
                        className="font-mono",
                    ),
                    ps.p(
                        f"Updated: {(q.data or {}).get('updated_at', '-')}",
                        className="text-xs text-gray-500",
                    ),
                )
            )
        ),
        ps.div(
            ps.button(
                "Burst async updates",
                onClick=page_state.burst,
                className="btn-primary mt-4",
            ),
        ),
        ps.div(
            ps.h3("View", className="font-semibold mt-4"),
            (
                ps.div(
                    ps.p("Overview shows the latest reading."),
                    className="text-sm text-gray-600",
                )
                if page_state.tab == "overview"
                else ps.div(
                    ps.p(
                        f"Trends placeholder — query calls so far: {city_state.calls}",
                        className="text-sm",
                    ),
                    ps.button(
                        "Refetch data",
                        onClick=q.refetch,
                        className="btn-secondary mt-2",
                    ),
                    className="p-3 bg-white rounded border mt-2",
                )
            ),
        ),
        className="p-4 bg-blue-50 rounded",
    )


# --- Layout and App ----------------------------------------------------------


@ps.component
def app_layout():
    # Sync layout units to session so children can read a single source of truth
    state = layout_state()
    return ps.div(
        ps.header(
            ps.div(
                ps.h1("Pulse Weather Demo", className="text-2xl font-bold"),
                ps.div(
                    ps.span(f"Units: {state.units}", className="mr-3"),
                    ps.button(
                        "Toggle Units",
                        onClick=state.toggle_units,
                        className="btn-secondary",
                    ),
                    className="flex items-center",
                ),
                className="flex justify-between items-center p-4 bg-gray-800 text-white",
            ),
            ps.nav(
                ps.Link("Home", to="/", className="nav-link"),
                className="flex justify-center space-x-4 p-3 bg-gray-700 text-white",
            ),
            className="mb-8",
        ),
        ps.main(ps.Outlet(), className="container mx-auto px-4"),
        className="min-h-screen bg-gray-100 text-gray-800",
    )


app = ps.App(
    routes=[
        ps.Layout(
            app_layout,
            children=[
                ps.Route("/", home),
                ps.Route("/city/:name", city_details),  # dynamic route
            ],
        )
    ],
    codegen=CodegenConfig(web_dir=Path(__file__).parent / "pulse-demo"),
)
