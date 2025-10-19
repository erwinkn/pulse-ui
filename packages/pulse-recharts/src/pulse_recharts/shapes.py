from collections.abc import Sequence
from typing import Literal, Unpack

import pulse as ps

from .common import AnimationTiming, LayoutType, NullableCoordinate

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
class CurveProps(ps.HTMLSVGProps, total=False):
	type: CurveType  # pyright: ignore[reportIncompatibleVariableOverride]
	"The interpolation type of the curve. Default: 'linear'"
	layout: LayoutType
	baseLine: float | Sequence[NullableCoordinate]
	points: Sequence[NullableCoordinate]  # pyright: ignore[reportIncompatibleVariableOverride]
	connectNulls: bool
	path: str
	# pathRef?: Ref<SVGPathElement>;


@ps.react_component("Curve", "recharts")
def Curve(key: str | None = None, **props: Unpack[CurveProps]): ...


# TODO: SVG <rect>
class RectangleProps(ps.HTMLSVGProps, total=False):
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


@ps.react_component("Rectangle", "recharts")
def Rectangle(key: str | None = None, **props: Unpack[RectangleProps]): ...
