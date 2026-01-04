"""
Lazy Import Demo - Demonstrates lazy imports for code-splitting.

This example shows:
1. Import(lazy=True) - Creates lazy import factories for React.lazy
2. import_() - Dynamic import primitive for @javascript functions
3. Constant + Jsx to create usable lazy React components

Run with: uv run pulse run examples/lazy_import.py
"""

import pulse as ps
from pulse.js.react import Suspense, lazy
from pulse.transpiler import Import, Jsx, javascript
from pulse.transpiler.dynamic_import import import_

# =============================================================================
# React imports
# =============================================================================

# =============================================================================
# Method 1: Import(lazy=True) + React.lazy + Constant + Jsx
# =============================================================================
# Import(lazy=True) creates a factory function.
# React.lazy() wraps it to create a lazy component.
# Constant() registers it so it's available in the registry.
# Jsx() makes it callable as a component.
#
# Generated JS:
#   const LineChart_1 = () => import("recharts").then(m => ({ default: m.LineChart }));
#   const LazyLineChart_2 = lazy(LineChart_1);

# Create lazy components
LazyLineChart = lazy(Import("LineChart", "recharts", lazy=True))
LazyBarChart = lazy(Import("BarChart", "recharts", lazy=True))

# Regular (eager) imports for chart children
XAxis = Jsx(Import("XAxis", "recharts"))
YAxis = Jsx(Import("YAxis", "recharts"))
Tooltip = Jsx(Import("Tooltip", "recharts"))
CartesianGrid = Jsx(Import("CartesianGrid", "recharts"))
ResponsiveContainer = Jsx(Import("ResponsiveContainer", "recharts"))
Line = Jsx(Import("Line", "recharts"))
Bar = Jsx(Import("Bar", "recharts"))


# =============================================================================
# Method 2: import_() in @javascript functions
# =============================================================================
# The import_() primitive provides inline dynamic imports.
#
# Generated JS: import("recharts").then(m => m.LineChart)


@javascript
def load_recharts_line():
	"""Load LineChart dynamically (example of import_ usage)."""
	return import_("recharts").then(lambda m: m.LineChart)


# =============================================================================
# Sample Data
# =============================================================================
CHART_DATA = [
	{"name": "Jan", "value": 400, "amt": 2400},
	{"name": "Feb", "value": 300, "amt": 2210},
	{"name": "Mar", "value": 600, "amt": 2290},
	{"name": "Apr", "value": 800, "amt": 2000},
	{"name": "May", "value": 500, "amt": 2181},
	{"name": "Jun", "value": 700, "amt": 2500},
]


# =============================================================================
# State
# =============================================================================
class DemoState(ps.State):
	chart_type: str = "none"  # "none", "line", "bar"

	def show_line_chart(self) -> None:
		self.chart_type = "line"

	def show_bar_chart(self) -> None:
		self.chart_type = "bar"

	def hide_chart(self) -> None:
		self.chart_type = "none"


# =============================================================================
# Components
# =============================================================================
@ps.component
def ChartDisplay(state: DemoState) -> ps.Element:
	"""Display the selected chart using lazy-loaded components."""
	if state.chart_type == "line":
		return ps.div(className="h-64")[
			ResponsiveContainer(width="100%", height="100%")[
				LazyLineChart(data=CHART_DATA)[
					CartesianGrid(strokeDasharray="3 3"),
					XAxis(dataKey="name"),
					YAxis(),
					Tooltip(),
					Line(
						type="monotone",
						dataKey="value",
						stroke="#10b981",
						strokeWidth=2,
					),
				]
			]
		]
	elif state.chart_type == "bar":
		return ps.div(className="h-64")[
			ResponsiveContainer(width="100%", height="100%")[
				LazyBarChart(data=CHART_DATA)[
					CartesianGrid(strokeDasharray="3 3"),
					XAxis(dataKey="name"),
					YAxis(),
					Tooltip(),
					Bar(
						dataKey="value",
						fill="#10b981",
					),
				]
			]
		]
	else:
		return ps.div(className="h-64 flex items-center justify-center text-slate-500")[
			"Click a button above to load a chart"
		]


@ps.component
def LazyImportDemo() -> ps.Element:
	with ps.init():
		state = DemoState()

	return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-8")[
		ps.div(className="mx-auto max-w-3xl space-y-6")[
			# Header
			ps.div(className="space-y-2")[
				ps.h1("Lazy Import Demo", className="text-3xl font-bold"),
				ps.p(
					"Demonstrates code-splitting with lazy imports for recharts components.",
					className="text-slate-400",
				),
			],
			# Method 1: Import(lazy=True)
			ps.div(className="rounded-lg border border-slate-800 p-6 space-y-4")[
				ps.h2(
					"Method 1: Import(lazy=True) + React.lazy",
					className="text-xl font-semibold text-emerald-400",
				),
				ps.p(
					"Creates a factory function, wraps with React.lazy, registers as Constant.",
					className="text-sm text-slate-400",
				),
				ps.div(className="space-y-2")[
					ps.p("Python:", className="text-xs text-slate-500"),
					ps.pre(
						"""ReactLazy = Import("lazy", "react")
LineChartFactory = Import("LineChart", "recharts", lazy=True)
_call = ReactLazy(LineChartFactory)
LazyLineChart = Jsx(Constant(_call, _call, "LazyLineChart"))""",
						className="bg-slate-900 rounded p-3 text-sm font-mono text-emerald-300",
					),
					ps.p("Generated JS:", className="text-xs text-slate-500 mt-2"),
					ps.pre(
						"""const LineChart_1 = () => import("recharts").then(m => ({ default: m.LineChart }));
const LazyLineChart_2 = lazy(LineChart_1);""",
						className="bg-slate-900 rounded p-2 text-xs font-mono text-slate-400",
					),
				],
			],
			# Method 2: import_()
			ps.div(className="rounded-lg border border-slate-800 p-6 space-y-4")[
				ps.h2(
					"Method 2: import_() in @javascript",
					className="text-xl font-semibold text-blue-400",
				),
				ps.p(
					"Inline dynamic imports for loading utilities or modules on demand.",
					className="text-sm text-slate-400",
				),
				ps.div(className="space-y-2")[
					ps.p("Python:", className="text-xs text-slate-500"),
					ps.pre(
						"""from pulse.transpiler.dynamic_import import import_

@javascript
def load_recharts_line():
    return import_("recharts").then(lambda m: m.LineChart)""",
						className="bg-slate-900 rounded p-3 text-sm font-mono text-blue-300",
					),
					ps.p("Generated JS:", className="text-xs text-slate-500 mt-2"),
					ps.pre(
						"""function load_recharts_line_1() {
  return import("recharts").then(m => m.LineChart);
}""",
						className="bg-slate-900 rounded p-2 text-xs font-mono text-slate-400",
					),
				],
			],
			# Interactive Demo
			ps.div(className="rounded-lg border border-slate-800 p-6 space-y-4")[
				ps.h2(
					"Live Demo (Lazy-Loaded Charts)", className="text-xl font-semibold"
				),
				ps.p(
					"Charts below use React.lazy - they load on demand!",
					className="text-xs text-slate-500",
				),
				ps.p(
					f"Current chart: {state.chart_type}",
					className="text-slate-400 font-mono text-sm mt-2",
				),
				ps.div(className="flex gap-3")[
					ps.button(
						"Line Chart",
						onClick=lambda: state.show_line_chart(),
						className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 transition-colors"
						+ (
							" ring-2 ring-emerald-400"
							if state.chart_type == "line"
							else ""
						),
					),
					ps.button(
						"Bar Chart",
						onClick=lambda: state.show_bar_chart(),
						className="rounded bg-blue-600 px-4 py-2 font-medium hover:bg-blue-500 transition-colors"
						+ (
							" ring-2 ring-blue-400" if state.chart_type == "bar" else ""
						),
					),
					ps.button(
						"Hide",
						onClick=lambda: state.hide_chart(),
						className="rounded bg-slate-700 px-4 py-2 font-medium hover:bg-slate-600 transition-colors",
					)
					if state.chart_type != "none"
					else None,
				],
				ps.div(className="mt-4 rounded-lg bg-slate-900 p-4")[
					Suspense(
						fallback=ps.div(
							className="h-64 flex items-center justify-center text-slate-500"
						)["Loading chart..."]
					)[ChartDisplay(state)]
				],
			],
			# Explanation
			ps.div(className="rounded-lg border border-slate-700 bg-slate-900/50 p-4")[
				ps.h3("How it works", className="font-semibold mb-2"),
				ps.ul(
					className="text-sm text-slate-400 space-y-1 list-disc list-inside"
				)[
					ps.li("Charts use React.lazy for code-splitting"),
					ps.li("React.Suspense shows fallback while chunk loads"),
					ps.li("Import(lazy=True) creates the dynamic import factory"),
					ps.li("Constant registers the lazy component in the JS registry"),
				],
			],
		]
	]


# =============================================================================
# App
# =============================================================================
app = ps.App([ps.Route("/", LazyImportDemo)])
