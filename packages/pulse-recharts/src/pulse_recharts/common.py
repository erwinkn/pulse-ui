from collections.abc import Callable
from typing import Any, Literal, TypedDict, TypeVar

import pulse as ps

T = TypeVar("T")
DataKey = str | int | ps.JsFunction[[T], str | int]


class ChartOffsetInternal(ps.JsObject):
	"""
	This object defines the offset of the chart area and width and height and brush and ... it's a bit too much information all in one.
	We use it internally but let's not expose it to the outside world.
	If you are looking for this information, instead import `ChartOffset` or `PlotArea` from `recharts`.
	"""

	top: float
	bottom: float
	left: float
	right: float
	width: float
	height: float
	brushBottom: float


class Coordinate(TypedDict):
	x: float
	y: float


class NullableCoordinate(TypedDict, total=False):
	x: float | None
	y: float | None


StackOffsetType = Literal["sign", "expand", "none", "wiggle", "silhouette", "positive"]

CartesianLayout = Literal["horizontal", "vertical"]

PolarLayout = Literal["centric", "radial"]

LayoutType = CartesianLayout | PolarLayout
"""
-- From the Recharts docs ---
DEPRECATED: use either CartesianLayout or PolarLayout instead.
Mixing both charts families leads to ambiguity in the type system.
These two layouts share very few properties, so it is best to keep them separate.
"""

AxisType = Literal["xAxis", "yAxis", "zAxis", "angleAxis", "radiusAxis"]

AxisDomainType = Literal["number", "category"]


class Margin(TypedDict):
	top: float | None
	right: float | None
	bottom: float | None
	left: float | None


class TickItem(TypedDict, total=False):
	value: Any
	coordinate: float
	index: int
	offset: float | None


TooltipIndex = str | None


class MouseHandlerDataParam(ps.JsObject):
	activeTooltipIndex: float | TooltipIndex | None
	"""Index of the active tick in the current chart. Only works with number-indexed one-dimensional data charts,
    like Line, Area, Bar, Pie, etc.

    Doesn't work with two-dimensional data charts like Treemap, Sankey. But one day it will which is why the TooltipIndex type is here.
    """

	isTooltipActive: bool

	activeIndex: float | TooltipIndex | None
	"""Exactly the same as activeTooltipIndex - this was also duplicated in recharts@2 so let's keep both properties for better backwards compatibility."""

	activeLabel: str | None
	activeDataKey: DataKey[Any] | None
	activeCoordinate: Coordinate | None


SyncMethod = (
	Literal["index", "value"] | Callable[[list[TickItem], MouseHandlerDataParam], float]
)
"""
Allows customisation of how the charts will synchronize tooltips and brushes.
Default: index

'index': other charts will reuse current datum's index within the data array. In cases where data does not have the same length, this might yield unexpected results.
'value': will try to match other charts values
custom function: will receive two arguments and should return an index of the active tick in the current chart:
argument 1: ticks from the current chart
argument 2: active tooltip state from the other chart
"""


class Rectangle(TypedDict):
	x: float | None
	y: float | None
	width: float
	height: float


AnimationTiming = Literal["ease", "ease-in", "ease-out", "ease-in-out", "linear"]


MinPointSize = float | ps.JsFunction[[float | None, int], float]
"A number or function (value: float | None, index: int) => minPointSize: float"
