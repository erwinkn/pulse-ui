from collections.abc import Sequence
from typing import Literal, TypedDict, Unpack

import pulse as ps
from pulse.dom.elements import GenericHTMLElement

from .common import AnimationTiming, Coordinate, LayoutType, NullableCoordinate
from .general import SymbolType

CurveType = Literal[
	"basis",
	"basisClosed",
	"basisOpen",
	"bumpX",
	"bumpY",
	"bump",
	"linear",
	"linearClosed",
	"natural",
	"monotoneX",
	"monotoneY",
	"monotone",
	"step",
	"stepBefore",
	"stepAfter",
	# CurveFactory, # -> D3 type that draws a curve on a canvas
]


# TODO: SVG <path> props
class CurveProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	type: CurveType  # pyright: ignore[reportIncompatibleVariableOverride]
	"The interpolation type of the curve. Default: 'linear'"
	layout: LayoutType
	baseLine: float | Sequence[NullableCoordinate]
	points: Sequence[NullableCoordinate]  # pyright: ignore[reportIncompatibleVariableOverride]
	connectNulls: bool
	path: str
	# pathRef?: Ref<SVGPathElement>;


@ps.react_component(ps.Import("Curve", "recharts"))
def Curve(key: str | None = None, **props: Unpack[CurveProps]): ...


# TODO: SVG <rect>
class RectangleProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	className: str
	x: float  # pyright: ignore[reportIncompatibleVariableOverride]
	y: float  # pyright: ignore[reportIncompatibleVariableOverride]
	width: float  # pyright: ignore[reportIncompatibleVariableOverride]
	height: float  # pyright: ignore[reportIncompatibleVariableOverride]
	radius: float | tuple[float, float]  # pyright: ignore[reportIncompatibleVariableOverride]
	isAnimationActive: bool
	isUpdateAnimationActive: bool
	animationBegin: float
	animationDuration: float
	animationEasing: AnimationTiming


@ps.react_component(ps.Import("Rectangle", "recharts"))
def Rectangle(key: str | None = None, **props: Unpack[RectangleProps]): ...


class SectorProps(TypedDict, total=False):
	className: str
	cx: float
	cy: float
	innerRadius: float
	outerRadius: float
	startAngle: float
	endAngle: float
	cornerRadius: float
	forceCornerRadius: bool
	cornerIsExternal: bool


@ps.react_component(ps.Import("Sector", "recharts"))
def Sector(key: str | None = None, **props: Unpack[SectorProps]): ...


class PolygonProps(TypedDict, total=False):
	className: str
	points: Sequence[Coordinate]
	baseLinePoints: Sequence[Coordinate]
	connectNulls: bool


@ps.react_component(ps.Import("Polygon", "recharts"))
def Polygon(key: str | None = None, **props: Unpack[PolygonProps]): ...


class DotProps(TypedDict, total=False):
	className: str
	cx: float
	cy: float
	r: float | str
	clipDot: bool


@ps.react_component(ps.Import("Dot", "recharts"))
def Dot(key: str | None = None, **props: Unpack[DotProps]): ...


class CrossProps(TypedDict, total=False):
	className: str
	x: float
	y: float
	width: float
	height: float
	top: float
	left: float


@ps.react_component(ps.Import("Cross", "recharts"))
def Cross(key: str | None = None, **props: Unpack[CrossProps]): ...


class SymbolsProps(TypedDict, total=False):
	className: str
	type: SymbolType
	cx: float
	cy: float
	size: float
	sizeType: Literal["area", "diameter"]


@ps.react_component(ps.Import("Symbols", "recharts"))
def Symbols(key: str | None = None, **props: Unpack[SymbolsProps]): ...


class TrapezoidProps(TypedDict, total=False):
	className: str
	x: float
	y: float
	upperWidth: float
	lowerWidth: float
	height: float
	isUpdateAnimationActive: bool
	animationBegin: float
	animationDuration: float
	animationEasing: AnimationTiming


@ps.react_component(ps.Import("Trapezoid", "recharts"))
def Trapezoid(key: str | None = None, **props: Unpack[TrapezoidProps]): ...
