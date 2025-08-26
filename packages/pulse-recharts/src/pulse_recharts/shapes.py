from typing import Literal, Optional, Sequence, TypedDict, Unpack
import pulse as ps
from .common import LayoutType, NullableCoordinate

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
