# pyright: reportUnusedFunction=false, reportMissingParameterType=false
"""
Debounced Callbacks Demo
========================
Compare immediate vs debounced input handlers and their callback counts.
"""

import pulse as ps


class DebounceState(ps.State):
	immediate_value: str
	debounced_value: str
	immediate_calls: int
	debounced_calls: int

	def __init__(self):
		self.immediate_value = ""
		self.debounced_value = ""
		self.immediate_calls = 0
		self.debounced_calls = 0

	def on_immediate(self, event):
		self.immediate_calls += 1
		self.immediate_value = event["target"]["value"]

	def on_debounced(self, event):
		self.debounced_calls += 1
		self.debounced_value = event["target"]["value"]


@ps.component
def DebouncedDemo():
	with ps.init():
		state = DebounceState()

	return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-8")[
		ps.div(className="mx-auto max-w-3xl space-y-6")[
			ps.div(className="space-y-2")[
				ps.h1("Debounced callbacks", className="text-3xl font-semibold"),
				ps.p(
					"Type in both inputs. The debounced handler only calls the server after you pause.",
					className="text-sm text-slate-300",
				),
			],
			ps.div(className="grid gap-6 md:grid-cols-2")[
				ps.div(className="rounded-xl border border-slate-800 bg-slate-900 p-5")[
					ps.h2("Immediate", className="text-lg font-semibold"),
					ps.p(
						"Server callback runs on every change.",
						className="text-xs text-slate-400",
					),
					ps.input(
						type="text",
						onChange=state.on_immediate,
						placeholder="Type quickly…",
						className="mt-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2",
					),
					ps.div(className="mt-3 text-sm text-slate-300")[
						ps.div(f"Callback count: {state.immediate_calls}"),
						ps.div(f"Value: {state.immediate_value or '—'}"),
					],
				],
				ps.div(className="rounded-xl border border-slate-800 bg-slate-900 p-5")[
					ps.h2("Debounced (300ms)", className="text-lg font-semibold"),
					ps.p(
						"Server callback runs after you stop typing.",
						className="text-xs text-slate-400",
					),
					ps.input(
						type="text",
						onChange=ps.debounced(state.on_debounced, 300),
						placeholder="Type quickly…",
						className="mt-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2",
					),
					ps.div(className="mt-3 text-sm text-slate-300")[
						ps.div(f"Callback count: {state.debounced_calls}"),
						ps.div(f"Value: {state.debounced_value or '—'}"),
					],
				],
			],
		],
	]


app = ps.App([ps.Route("/", DebouncedDemo)])
