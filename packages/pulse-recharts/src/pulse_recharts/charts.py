from typing import Any, Generic, TypedDict, TypeVar, Unpack

import pulse as ps
from pulse.html.elements import GenericHTMLElement

from .common import (
	CartesianLayout,
	DataKey,
	Margin,
	PolarLayout,
	StackOffsetType,
	SyncMethod,
)

T = TypeVar("T")


class CartesianChartProps(TypedDict, Generic[T], total=False):
	accessibilityLayer: bool
	barCategoryGap: float | str
	barGap: float | str
	barSize: float | str
	className: str
	compact: bool
	data: list[T]
	dataKey: DataKey[T]
	desc: str
	height: float
	id: str
	layout: CartesianLayout
	margin: Margin
	maxBarSize: float
	reverseStackOrder: bool
	role: str
	stackOffset: StackOffsetType
	style: ps.CSSProperties
	syncId: float | str
	syncMethod: SyncMethod
	tabIndex: float
	throttleDelay: float
	title: str
	width: float


class PolarChartProps(TypedDict, Generic[T]):
	accessibilityLayer: bool
	barCategoryGap: float | str
	barGap: float | str
	barSize: float | str
	className: str
	cx: float | str
	cy: float | str
	data: list[T]
	dataKey: DataKey[T]
	desc: str
	endAngle: float
	height: float
	id: str
	innerRadius: float | str
	layout: PolarLayout
	margin: Margin
	maxBarSize: float
	outerRadius: float | str
	reverseStackOrder: bool
	role: str
	stackOffset: StackOffsetType
	startAngle: float
	style: ps.CSSProperties
	syncId: float | str
	syncMethod: SyncMethod
	tabIndex: float
	throttleDelay: float
	title: str
	width: float


# TODO: All charts are <svg> elements


class AreaChartProps(ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]): ...  # pyright: ignore[reportIncompatibleVariableOverride]


@ps.react_component("AreaChart", "recharts")
def AreaChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[AreaChartProps]
): ...


class BarChartProps(ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]): ...  # pyright: ignore[reportIncompatibleVariableOverride]


@ps.react_component("BarChart", "recharts")
def BarChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[BarChartProps]
): ...


class LineChartProps(ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]): ...  # pyright: ignore[reportIncompatibleVariableOverride]


@ps.react_component("LineChart", "recharts")
def LineChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[LineChartProps]
): ...


class ComposedChartProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]
): ...


@ps.react_component("ComposedChart", "recharts")
def ComposedChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[ComposedChartProps]
): ...


class PieChartProps(ps.HTMLSVGProps[GenericHTMLElement], PolarChartProps[Any]): ...  # pyright: ignore[reportIncompatibleVariableOverride]


@ps.react_component("PieChart", "recharts")
def PieChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[PieChartProps]
): ...


class RadarChartProps(ps.HTMLSVGProps[GenericHTMLElement], PolarChartProps[Any]): ...  # pyright: ignore[reportIncompatibleVariableOverride]


@ps.react_component("RadarChart", "recharts")
def RadarChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[RadarChartProps]
): ...


class RadialBarChartProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLSVGProps[GenericHTMLElement], PolarChartProps[Any]
): ...


@ps.react_component("RadialBarChart", "recharts")
def RadialBarChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[RadialBarChartProps]
): ...


class ScatterChartProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]
): ...


@ps.react_component("ScatterChart", "recharts")
def ScatterChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[ScatterChartProps]
): ...


class FunnelChartProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLSVGProps[GenericHTMLElement], CartesianChartProps[Any]
): ...


@ps.react_component("FunnelChart", "recharts")
def FunnelChart(
	*children: ps.Child, key: str | None = None, **props: Unpack[FunnelChartProps]
): ...


# TODO:
# - Treemap
# - Sankey
