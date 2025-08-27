from re import A
from typing import Any, Callable, Literal, Optional, Sequence, TypedDict, Union, Unpack
import pulse as ps
from .common import AnimationTiming, ChartOffsetInternal, DataKey, MinPointSize
from .general import LegendType, AnimationEasing
from .shapes import CurveProps, RectangleProps

# Placeholder for TooltipType until a concrete definition is provided
TooltipType = Any


class XAxisPaddingDict(TypedDict, total=False):
    left: float
    right: float


XAxisPadding = Union[XAxisPaddingDict, Literal["gap", "no-gap"]]


class YAxisPaddingDict(TypedDict, total=False):
    top: float
    bottom: float


YAxisPadding = Union[YAxisPaddingDict, Literal["gap", "no-gap"]]

XAxisOrientation = Literal["top", "bottom"]
YAxisOrientation = Literal["left", "right"]
# TODO: SVGProps<SVGTextElement>.
# THe elements have to be SVG elements
TickProp = ps.HTMLSVGProps | ps.Element | ps.JsFunction[[Any], ps.Element] | bool

AxisInterval = Union[
    float,
    Literal[
        "preserveStart", "preserveEnd", "preserveStartEnd", "equidistantPreserveStart"
    ],
]
"""Defines how ticks are placed and whether / how tick collisions are handled.

'preserveStart' keeps the left tick on collision and ensures that the first tick is always shown.
'preserveEnd' keeps the right tick on collision and ensures that the last tick is always shown. 
'preserveStartEnd' keeps the left tick on collision and ensures that the first and last ticks always show.
'equidistantPreserveStart' selects a number N such that every nTh tick will be shown without collision.
"""

AxisTick = Union[float, str]
"""Ticks can be any type when the axis is the type of category.

Ticks must be numbers when the axis is the type of number.
"""

AxisDomainType = Literal["number", "category"]

ScaleType = Literal[
    "auto",
    "linear",
    "pow",
    "sqrt",
    "log",
    "symlog",
    "identity",
    "time",
    "band",
    "point",
    "ordinal",
    "quantile",
    "quantize",
    "utc",
    "sequential",
    "threshold",
]

AxisDomainItem = (
    str | float | Callable[[float], str | float] | Literal["auto", "dataMin", "dataMax"]
)
AxisDomain = (
    Sequence[str | float]
    | tuple[AxisDomainItem, AxisDomainItem]
    # ([dataMin, dataMax]: tuple[float, float], allowDataOverflow: bool) => tuple[float, float]
    | Callable[[tuple[float, float], bool], tuple[float, float]]
)
"""The domain of axis.
This is the definition

Numeric domain is always defined by an array of exactly two values, for the min and the max of the axis.
Categorical domain is defined as array of all possible values.

Can be specified in many ways:
- array of numbers 
- with special strings like 'dataMin' and 'dataMax'
- with special string math like 'dataMin - 100'
- with keyword 'auto'
- or a function
- array of functions
- or a combination of the above
"""


class BaseAxisProps(TypedDict, total=False):
    type: AxisDomainType
    """The type of axis"""

    dataKey: DataKey
    """The key of data displayed in the axis"""

    hide: bool
    """Whether display the axis"""

    scale: ScaleType  # Also allows a RechartsScale interface but we can't implement that ATM
    """The scale type as a string, or scale function"""

    tick: TickProp
    """The option for tick"""

    tickCount: int
    """The count of ticks"""

    # TODO: This is SVGProps<SVGLineElement>
    axisLine: Union[bool, ps.HTMLSVGProps]
    """The option for axisLine"""

    # TODO: This is SVGProps<SVGLineElement>
    tickLine: Union[bool, ps.HTMLSVGProps]
    """The option for tickLine"""

    tickSize: float
    """The size of tick line"""

    tickFormatter: ps.JsFunction[[Any, int], str]
    """The formatter function of tick"""

    allowDataOverflow: bool
    """When domain of the axis is specified and the type of the axis is 'number',
    if allowDataOverflow is set to be false, the domain will be adjusted when the
    minimum value of data is smaller than domain[0] or the maximum value of data
    is greater than domain[1] so that the axis displays all data values. If set
    to true, graphic elements (line, area, bars) will be clipped to conform to
    the specified domain."""

    allowDuplicatedCategory: bool
    """Allow the axis has duplicated categories or not when the type of axis is
    "category"."""

    allowDecimals: bool
    """Allow the ticks of axis to be decimals or not."""

    domain: AxisDomain
    """The domain of scale in this axis"""

    includeHidden: bool
    """Consider hidden elements when computing the domain (defaults to false)"""

    name: str
    """The name of data displayed in the axis"""

    unit: str
    """The unit of data displayed in the axis"""

    range: tuple[float, float]
    """The range of the axis"""

    AxisComp: Any
    """axis react component"""

    label: Union[str, int, ps.Element, dict]
    """Needed to allow usage of the label prop on the X and Y axis"""

    className: str
    """The HTML element's class name"""


class XAxisProps(BaseAxisProps, ps.HTMLSVGProps, total=False):
    xAxisId: Union[str, float]
    """The unique id of x-axis"""

    height: float
    """The height of axis, which need to be set by user"""

    mirror: bool
    """Whether to mirror the axis"""

    orientation: XAxisOrientation
    """The orientation of the axis"""

    ticks: list[AxisTick]
    """Ticks can be any type when the axis is the type of category
    Ticks must be numbers when the axis is the type of number"""

    padding: XAxisPadding
    """Padding of the axis"""

    minTickGap: float
    """The minimum gap between two adjacent ticks"""

    interval: AxisInterval
    """The interval of ticks"""

    reversed: bool
    """Whether to reverse the axis"""

    angle: float
    """The rotate angle of tick"""

    tickMargin: float
    """The margin between tick line and tick"""


@ps.react_component("XAxis", "recharts")
def XAxis(key: Optional[str] = None, **props: Unpack[XAxisProps]): ...


class YAxisProps(BaseAxisProps, ps.HTMLSVGProps, total=False):
    yAxisId: Union[str, float]
    """The unique id of y-axis"""

    width: Union[float, Literal["auto"]]
    """The width of axis, which need to be set by user.
    When set to 'auto', the width will be calculated dynamically based on tick labels and axis labels."""

    mirror: bool
    """Whether to mirror the axis"""

    orientation: YAxisOrientation
    """The orientation of the axis"""

    ticks: list[AxisTick]
    """Ticks can be any type when the axis is the type of category
    Ticks must be numbers when the axis is the type of number"""

    padding: YAxisPadding
    """Padding of the axis"""

    minTickGap: float
    """The minimum gap between two adjacent ticks"""

    interval: AxisInterval
    """The interval of ticks"""

    reversed: bool
    """Whether to reverse the axis"""

    tickMargin: float
    """The margin between tick line and tick"""

    angle: float
    """The rotate angle of tick"""


@ps.react_component("YAxis", "recharts")
def YAxis(key: Optional[str] = None, **props: Unpack[YAxisProps]): ...


# TODO
class AxisPropsForCartesianGridTicksGeneration(ps.JsObject): ...


class HorizontalCoordinateProps(ps.JsObject):
    yAxis: AxisPropsForCartesianGridTicksGeneration
    width: float
    height: float
    offset: ChartOffsetInternal


class VerticalCoordinateProps(ps.JsObject):
    xAxis: AxisPropsForCartesianGridTicksGeneration
    width: float
    height: float
    offset: ChartOffsetInternal


# TODO
class GridLineTypeFunctionProps(ps.JsObject): ...


# SVGLineElementProps in practice
GridLineType = (
    ps.HTMLSVGProps
    | ps.Element
    | bool
    | Callable[[GridLineTypeFunctionProps], ps.Element]
)


class CartesianGridProps(ps.HTMLSVGProps, total=False):
    x: float
    """The x-coordinate of grid.
    If left undefined, it will be computed from the chart's offset and margins."""

    y: float
    """The y-coordinate of grid.
    If left undefined, it will be computed from the chart's offset and margins."""

    horizontal: GridLineType
    """The horizontal grid line type"""

    vertical: GridLineType
    """The vertical grid line type"""

    horizontalPoints: list[float]
    """Array of coordinates in pixels where to draw horizontal grid lines.
    Has priority over syncWithTicks and horizontalValues."""

    verticalPoints: list[float]
    """Array of coordinates in pixels where to draw vertical grid lines.
    Has priority over syncWithTicks and horizontalValues."""

    verticalFill: list[str]
    """Defines background color of stripes.

    The values from this array will be passed in as the `fill` property in a `rect` SVG element.
    For possible values see: https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/fill#rect

    In case there are more stripes than colors, the colors will start from beginning.
    So for example: verticalFill['yellow', 'black'] produces a pattern of yellow|black|yellow|black

    If this is undefined, or an empty array, then there is no background fill.
    Note: Grid lines will be rendered above these background stripes."""

    horizontalFill: list[str]
    """Defines background color of stripes.

    The values from this array will be passed in as the `fill` property in a `rect` SVG element.
    For possible values see: https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/fill#rect

    In case there are more stripes than colors, the colors will start from beginning.
    So for example: horizontalFill['yellow', 'black'] produces a pattern of yellow|black|yellow|black

    If this is undefined, or an empty array, then there is no background fill.
    Note: Grid lines will be rendered above these background stripes."""

    syncWithTicks: bool
    """If true, only the lines that correspond to the axes ticks values will be drawn.
    If false, extra lines could be added for each axis (at min and max coordinates), if there will not such ticks.
    horizontalPoints, verticalPoints, horizontalValues, verticalValues have priority over syncWithTicks."""

    horizontalValues: Union[list[float], list[str]]
    """Array of values, where horizontal lines will be drawn. Numbers or strings, in dependence on axis type.
    Has priority over syncWithTicks but not over horizontalValues."""

    verticalValues: Union[list[float], list[str]]
    """Array of values, where vertical lines will be drawn. Numbers or strings, in dependence on axis type.
    Has priority over syncWithTicks but not over verticalValues."""

    xAxisId: str | int
    """The ID of the x-axis. Default: 0."""

    yAxisId: str | int
    """The ID of the y-axis. Default: 0."""

    # === Internal props (but somehow in the public docs??) ===

    width: float
    height: float
    horizontalCoordinatesGenerator: Callable[
        [HorizontalCoordinateProps, bool], list[float]
    ]
    "(props: HorizontalCoordinateProps, syncWithTicks: bool) -> coordinates: list[float]"
    verticalCoordinatesGenerator: Callable[[VerticalCoordinateProps, bool], list[float]]
    "(props: VerticalCoordinateProps, syncWithTicks: bool) -> coordinates: list[float]"


@ps.react_component("CartesianGrid", "recharts")
def CartesianGrid(key: Optional[str] = None, **props: Unpack[CartesianGridProps]): ...


class LinePointItem(ps.JsObject):
    value: float
    payload: Any | None
    """Arbitrary data point payload associated with this coordinate, if any."""

    # Some points can have gaps (null coordinates) when connectNulls is False
    x: float | None
    y: float | None


# Visual dot configuration used for points and active points
ActiveDotType = ps.HTMLSVGProps | ps.Element | bool | ps.JsFunction[[Any], ps.Element]


LineLayout = Literal["horizontal", "vertical"]


class LineProps(CurveProps, total=False):
    dataKey: DataKey
    """The key or getter of a group of data which should be unique in a LineChart."""

    xAxisId: str | int
    """The id of the x-axis corresponding to the data. Default: 0"""

    yAxisId: str | int
    """The id of the y-axis corresponding to the data. Default: 0"""

    legendType: LegendType
    """The type of icon in the legend. If set to 'none', no legend item will be rendered.
    Default: 'line'"""

    dot: ActiveDotType
    """Controls rendering of point dots.
    - False: no dots
    - True: default dots
    - Object: merges with internally calculated props
    - Element: custom dot element
    - Function: called to render a customized dot
    Default: True"""

    activeDot: ActiveDotType
    """Controls rendering of the active dot when tooltip is active.
    Same options as 'dot'. Default: True"""

    label: bool | dict | ps.Element | ps.JsFunction[[Any], ps.Element]
    """Controls rendering of labels on the line points.
    - False: no labels
    - True: default labels
    - Object: merges with internally calculated props
    - Element: custom label element
    - Function: called to render a customized label
    Default: False"""

    hide: bool
    """Hides the line when True (useful for toggling via legend). Default: False"""

    points: list[LinePointItem]
    """The coordinates of all points in the line. Usually calculated internally."""

    layout: LineLayout
    """Layout of the line, usually inherited from parent chart: 'horizontal' | 'vertical'"""

    connectNulls: bool
    """Whether to connect the line across null points. Default: False"""

    unit: str | int
    """The unit of data. Used in tooltip."""

    name: str | int
    """The name of the data series. Used in tooltip and legend. If unset, the value of dataKey is used."""

    isAnimationActive: bool
    """If False, animation of line is disabled. Default: True in CSR, False in SSR"""

    animateNewValues: bool
    """Animate updates when data values change. Default: implementation-defined (follows Recharts)."""

    animationBegin: int
    """When the animation should begin (ms). Default: 0"""

    animationDuration: int
    """Duration of the animation (ms). Default: 1500"""

    animationEasing: AnimationEasing
    """Type of easing function. Default: 'ease'"""

    # I think this is unused, only type allowed is "none"
    # tooltipType: "TooltipType"
    """The type of tooltip to show for this series."""

    data: Any
    """Series data input. Usually inherited from parent chart."""


@ps.react_component("Line", "recharts")
def Line(key: Optional[str] = None, **props: Unpack[LineProps]): ...


class BarProps(RectangleProps, total=False):
    className: str
    index: str | int
    xAxisId: str | int
    yAxisId: str | int
    stackId: str | int
    barSize: str | float
    unit: str | int
    name: str | int
    dataKey: DataKey
    tooltipType: TooltipType
    legendType: LegendType
    minPointSize: MinPointSize
    maxBarSize: float
    hide: bool
    shape: "ActiveBar"
    activeBar: "ActiveBar"
    background: "ActiveBar"
    radius: float | tuple[float, float, float, float]
    # NO argument event handlers
    onAnimationStart: ps.EventHandler
    onAnimationEnd: ps.EventHandler
    isAnimationActive: bool
    animationBegin: float
    animationDuration: float
    animationEasing: AnimationTiming
    id: str
    # Convoluted type where I think it's better to just use Label or LabelList
    # label: bool | str | float


ActiveBar = bool | ps.Element | ps.JsFunction[[BarProps], ps.Element]
