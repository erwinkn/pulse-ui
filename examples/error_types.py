from typing import cast, get_args

import pulse as ps

ERROR_CODES = cast(tuple[ps.ErrorCode, ...], tuple(get_args(ps.ErrorCode)))


class ErrorTypesState(ps.State):
	last_code: str = ""
	trigger_count: int = 0
	history: list[str] = []

	def trigger(self, code: ps.ErrorCode):
		self.last_code = code
		self.trigger_count += 1
		self.history = [code, *self.history[:19]]

		try:
			raise RuntimeError(f"Example error for code '{code}'")
		except RuntimeError as exc:
			ps.PulseContext.get().errors.report(
				exc,
				code=code,
				details={
					"example": "error_types",
					"trigger": "manual",
				},
			)


@ps.component
def ErrorTypesDemo():
	with ps.init():
		state = ErrorTypesState()

	return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-6")[
		ps.div(className="mx-auto max-w-5xl space-y-6")[
			ps.div(className="space-y-2")[
				ps.h1("Pulse Error Codes", className="text-3xl font-bold"),
				ps.p(
					"Trigger each server error code and inspect Pulse error transport/log output.",
					className="text-slate-300",
				),
				ps.p(
					f"Total triggers: {state.trigger_count} | Last code: {state.last_code or '-'}",
					className="text-sm text-slate-400",
				),
			],
			ps.div(className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3")[
				ps.For(
					ERROR_CODES,
					lambda code, _idx: ps.button(
						code,
						key=code,
						onClick=lambda: state.trigger(code),
						className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-left text-sm hover:border-emerald-400",
					),
				)
			],
			ps.div(className="rounded border border-slate-800 bg-slate-900 p-4")[
				ps.h2("Recent Triggers", className="mb-2 text-lg font-semibold"),
				ps.For(
					state.history,
					lambda item, idx: ps.div(
						f"{idx + 1}. {item}",
						key=f"{item}-{idx}",
						className="font-mono text-sm text-slate-300",
					),
				)
				if state.history
				else ps.p("No triggers yet.", className="text-slate-400"),
			],
		]
	]


app = ps.App([ps.Route("/", ErrorTypesDemo)])
