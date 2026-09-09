import importlib

import pulse_recharts as pr
from pulse.requirements import get_requirements
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element

COMPONENT_NAMES = [
	"Surface",
	"Layer",
	"Legend",
	"DefaultLegendContent",
	"Tooltip",
	"DefaultTooltipContent",
	"ResponsiveContainer",
	"Cell",
	"Text",
	"Label",
	"LabelList",
	"Customized",
	"ZIndexLayer",
	"Sector",
	"Curve",
	"Rectangle",
	"Polygon",
	"Dot",
	"Cross",
	"Symbols",
	"Trapezoid",
	"PolarGrid",
	"PolarRadiusAxis",
	"PolarAngleAxis",
	"Pie",
	"Radar",
	"RadialBar",
	"Brush",
	"ReferenceLine",
	"ReferenceDot",
	"ReferenceArea",
	"CartesianAxis",
	"CartesianGrid",
	"Line",
	"Area",
	"Bar",
	"BarStack",
	"Scatter",
	"XAxis",
	"YAxis",
	"ZAxis",
	"ErrorBar",
	"LineChart",
	"BarChart",
	"PieChart",
	"Treemap",
	"Sankey",
	"RadarChart",
	"ScatterChart",
	"AreaChart",
	"RadialBarChart",
	"ComposedChart",
	"SunburstChart",
	"Funnel",
	"FunnelChart",
]


def test_recharts_components_exported() -> None:
	for name in COMPONENT_NAMES:
		component = getattr(pr, name)
		element = component()
		assert isinstance(element, Element)
		assert isinstance(element.tag, Import)
		assert element.tag.src == "recharts"
		assert element.tag.name == name


def test_require_does_not_register_pulse_recharts_npm_package() -> None:
	# Other tests may have cleared the global require registry.
	importlib.reload(pr)
	required = dict(get_requirements())
	assert "pulse-recharts" not in required
	assert required["recharts"] == ">=3.7.0"
