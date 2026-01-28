# pyright: reportUnusedFunction=false, reportMissingParameterType=false
"""
Query Param State Demo
======================
Demonstrates ps.QueryParam bindings that sync state to the URL.
"""

from datetime import date, datetime, timezone

import pulse as ps


class QueryState(ps.State):
	q: ps.QueryParam[str] = ""
	page: ps.QueryParam[int] = 1
	tags: ps.QueryParam[list[str]] = []
	since: ps.QueryParam[date | None] = None
	updated: ps.QueryParam[datetime | None] = None

	def set_query(self, value: str) -> None:
		self.q = value

	def next_page(self) -> None:
		self.page += 1

	def prev_page(self) -> None:
		self.page = max(1, self.page - 1)

	def add_tag(self, tag: str) -> None:
		if tag in self.tags:
			return
		self.tags = [*self.tags, tag]

	def clear_tags(self) -> None:
		self.tags = []

	def set_since_today(self) -> None:
		self.since = date.today()

	def clear_since(self) -> None:
		self.since = None

	def set_updated_now(self) -> None:
		self.updated = datetime.now(timezone.utc)

	def clear_updated(self) -> None:
		self.updated = None


@ps.component
def QueryParamDemo():
	with ps.init():
		state = QueryState()

	route = ps.route()

	return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-8")[
		ps.div(className="mx-auto max-w-2xl space-y-6")[
			ps.div(className="space-y-2")[
				ps.h1("Query Param State", className="text-3xl font-semibold"),
				ps.p(
					"Edits below update the URL. Editing the URL updates state.",
					className="text-sm text-slate-400",
				),
			],
			ps.div(className="space-y-2")[
				ps.label("Search", className="text-sm font-medium text-slate-300"),
				ps.input(
					value=state.q,
					onChange=lambda event: state.set_query(event["target"]["value"]),
					placeholder="Try typing here",
					className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2",
				),
			],
			ps.div(className="flex flex-wrap items-center gap-3")[
				ps.button(
					"Prev page",
					onClick=state.prev_page,
					className="rounded border border-slate-700 px-3 py-1",
				),
				ps.span(f"Page: {state.page}", className="text-sm"),
				ps.button(
					"Next page",
					onClick=state.next_page,
					className="rounded border border-slate-700 px-3 py-1",
				),
			],
			ps.div(className="space-y-2")[
				ps.div(className="flex flex-wrap gap-2")[
					ps.button(
						"Add tag: alpha",
						onClick=lambda: state.add_tag("alpha"),
						className="rounded border border-emerald-500 px-3 py-1 text-emerald-200",
					),
					ps.button(
						"Add tag: a,b",
						onClick=lambda: state.add_tag("a,b"),
						className="rounded border border-emerald-500 px-3 py-1 text-emerald-200",
					),
					ps.button(
						"Clear tags",
						onClick=state.clear_tags,
						className="rounded border border-slate-700 px-3 py-1",
					),
				],
				ps.div(
					f"Tags: {', '.join(state.tags) if state.tags else '—'}",
					className="text-sm text-slate-300",
				),
			],
			ps.div(className="grid gap-2 sm:grid-cols-2")[
				ps.div(className="space-y-2 rounded border border-slate-800 p-3")[
					ps.div(
						"Since (date)", className="text-xs uppercase text-slate-400"
					),
					ps.div(
						state.since.isoformat() if state.since else "—",
						className="text-sm",
					),
					ps.div(className="flex gap-2")[
						ps.button(
							"Set today",
							onClick=state.set_since_today,
							className="rounded border border-slate-700 px-2 py-1 text-xs",
						),
						ps.button(
							"Clear",
							onClick=state.clear_since,
							className="rounded border border-slate-700 px-2 py-1 text-xs",
						),
					],
				],
				ps.div(className="space-y-2 rounded border border-slate-800 p-3")[
					ps.div(
						"Updated (datetime)",
						className="text-xs uppercase text-slate-400",
					),
					ps.div(
						state.updated.isoformat() if state.updated else "—",
						className="text-sm break-all",
					),
					ps.div(className="flex gap-2")[
						ps.button(
							"Set now",
							onClick=state.set_updated_now,
							className="rounded border border-slate-700 px-2 py-1 text-xs",
						),
						ps.button(
							"Clear",
							onClick=state.clear_updated,
							className="rounded border border-slate-700 px-2 py-1 text-xs",
						),
					],
				],
			],
			ps.div(
				className="rounded border border-slate-800 bg-slate-900 p-3 text-xs"
			)[
				ps.div("Route info", className="text-slate-400"),
				ps.div(f"query: {route.query}"),
				ps.div(f"queryParams: {route.queryParams}"),
			],
		],
	]


app = ps.App([ps.Route("/", QueryParamDemo)])
