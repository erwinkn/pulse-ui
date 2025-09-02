from typing import Literal, Optional, Sequence, TypedDict, Unpack
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
    type: CurveType
    "The interpolation type of the curve. Default: 'linear'"
    layout: LayoutType
    baseLine: float | Sequence[NullableCoordinate]
    points: Sequence[NullableCoordinate]
    connectNulls: bool
    path: str
    # pathRef?: Ref<SVGPathElement>;


@ps.react_component("Curve", "recharts")
def Curve(key: Optional[str] = None, **props: Unpack[CurveProps]): ...


# TODO: SVG <rect>
class RectangleProps(ps.HTMLSVGProps, total=False):
    className: str
    x: float
    y: float
    width: float
    height: float
    radius: float | tuple[float, float]
    isAnimationActive: bool
    isUpdateAnimationActive: bool
    animationBegin: float
    animationDuration: float
    animationEasing: AnimationTiming


@ps.react_component("Rectangle", "recharts")
def Rectangle(key: Optional[str] = None, **props: Unpack[RectangleProps]): ...
