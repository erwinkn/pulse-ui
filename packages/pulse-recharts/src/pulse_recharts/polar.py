from typing import Any, Literal, TypedDict, Unpack

import pulse as ps

from .cartesian import AxisDomain, AxisDomainType, ScaleType, TickProp
from .common import DataKey
from .general import AnimationEasing, LegendType


class PolarGridProps(TypedDict, total=False):
	cx: float
	cy: float
	innerRadius: float | str
	outerRadius: float | str
	polarAngles: list[float]
	polarRadius: list[float]
	gridType: Literal["polygon", "circle"]
	radialLines: bool
	angleAxisId: str | int
	radiusAxisId: str | int
	zIndex: int


@ps.react_component(ps.Import("PolarGrid", "recharts"))
def PolarGrid(key: str | None = None, **props: Unpack[PolarGridProps]): ...


class PolarAngleAxisProps(TypedDict, total=False):
	dataKey: DataKey[Any]
	angleAxisId: str | int
	cx: float
	cy: float
	radius: float | str
	axisLine: bool | dict[str, Any]
	tick: TickProp
	tickFormatter: ps.JsFunction[Any, int, str]
	tickCount: int
	orientation: Literal["inner", "outer"]
	type: AxisDomainType
	domain: AxisDomain
	scale: ScaleType
	zIndex: int


@ps.react_component(ps.Import("PolarAngleAxis", "recharts"))
def PolarAngleAxis(key: str | None = None, **props: Unpack[PolarAngleAxisProps]): ...


class PolarRadiusAxisProps(TypedDict, total=False):
	angle: float
	radiusAxisId: str | int
	cx: float
	cy: float
	domain: AxisDomain
	scale: ScaleType
	tick: TickProp
	tickFormatter: ps.JsFunction[Any, int, str]
	tickCount: int
	orientation: Literal["inner", "outer"]
	axisLine: bool | dict[str, Any]
	zIndex: int


@ps.react_component(ps.Import("PolarRadiusAxis", "recharts"))
def PolarRadiusAxis(key: str | None = None, **props: Unpack[PolarRadiusAxisProps]): ...


PieLabel = bool | dict[str, Any] | ps.Element | ps.JsFunction[Any, ps.Element]
PieShape = bool | dict[str, Any] | ps.Element | ps.JsFunction[Any, ps.Element]


class PieProps(TypedDict, total=False):
	data: list[Any]
	dataKey: DataKey[Any]
	nameKey: DataKey[Any]
	cx: float | str
	cy: float | str
	innerRadius: float | str
	outerRadius: float | str
	startAngle: float
	endAngle: float
	paddingAngle: float
	cornerRadius: float | str
	minAngle: float
	label: PieLabel
	labelLine: PieLabel
	legendType: LegendType
	tooltipType: Literal["none"]
	activeIndex: int
	activeShape: PieShape
	isAnimationActive: bool | Literal["auto"]
	animationBegin: int
	animationDuration: int
	animationEasing: AnimationEasing
	fill: str
	stroke: str
	onMouseEnter: ps.JsFunction[Any, Any]
	onMouseLeave: ps.JsFunction[Any, Any]
	onClick: ps.JsFunction[Any, Any]


@ps.react_component(ps.Import("Pie", "recharts"))
def Pie(key: str | None = None, **props: Unpack[PieProps]): ...


class RadarProps(TypedDict, total=False):
	dataKey: DataKey[Any]
	name: str | int
	legendType: LegendType
	tooltipType: Literal["none"]
	dot: bool | ps.Element | ps.JsFunction[Any, ps.Element]
	activeDot: bool | ps.Element | ps.JsFunction[Any, ps.Element]
	connectNulls: bool
	isAnimationActive: bool | Literal["auto"]
	animationBegin: int
	animationDuration: int
	animationEasing: AnimationEasing
	fill: str
	fillOpacity: float
	stroke: str
	label: bool | dict[str, Any] | ps.Element | ps.JsFunction[Any, ps.Element]


@ps.react_component(ps.Import("Radar", "recharts"))
def Radar(key: str | None = None, **props: Unpack[RadarProps]): ...


class RadialBarProps(TypedDict, total=False):
	dataKey: DataKey[Any]
	name: str | int
	legendType: LegendType
	tooltipType: Literal["none"]
	minAngle: float
	clockWise: bool
	background: bool | ps.Element | ps.JsFunction[Any, ps.Element]
	label: bool | dict[str, Any] | ps.Element | ps.JsFunction[Any, ps.Element]
	cornerRadius: float | str
	fill: str
	stroke: str
	isAnimationActive: bool | Literal["auto"]
	animationBegin: int
	animationDuration: int
	animationEasing: AnimationEasing


@ps.react_component(ps.Import("RadialBar", "recharts"))
def RadialBar(key: str | None = None, **props: Unpack[RadialBarProps]): ...
