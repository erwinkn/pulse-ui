from dataclasses import dataclass
from typing import (
    Generic,
    Literal,
    Optional,
    TypeVar,
    TypedDict,
    Union,
    Unpack,
)
import pulse as ps
from pulse.html.props import HTMLSVGProps
from .common import DataKey

T = TypeVar("T")


class DimensionRequired(TypedDict):
    width: float
    height: float


class Dimension(TypedDict, total=False):
    width: Optional[float]
    height: Optional[float]


class CartesianViewBox(TypedDict, total=False):
    x: float
    y: float
    width: float
    height: float


class CartesianViewBoxRequired(TypedDict):
    x: float
    y: float
    width: float
    height: float


class PolarViewBox(TypedDict, total=False):
    cx: float
    cy: float
    innerRadius: float
    outerRadius: float
    startAngle: float
    endAngle: float
    clockWise: bool


class PolarViewBoxRequired(TypedDict):
    cx: float
    cy: float
    innerRadius: float
    outerRadius: float
    startAngle: float
    endAngle: float
    clockWise: bool


ViewBox = CartesianViewBox | PolarViewBox
ViewBoxRequired = CartesianViewBoxRequired | PolarViewBoxRequired


class ResponsiveContainerProps(ps.HTMLProps, total=False):
    # HTML props
    id: str
    # className: str
    style: ps.CSSProperties

    aspect: float
    """width / height. If specified, the height will be calculated by width /
    aspect."""

    width: float | str
    """The percentage value of the chart's width or a fixed width. Default:
    '100%'"""

    height: float | str
    """The percentage value of the chart's width or a fixed height. Default:
    '100%'"""

    minWidth: float
    """The minimum width of the container."""

    minHeight: float
    """The minimum height of the container."""

    maxHeight: float
    """The maximum height of the container."""

    debounce: int
    """If specified a positive number, debounced function will be used to handle
    the resize event. Default: 0"""

    onResize: ps.EventHandler2[float, float]  # pyright: ignore[reportIncompatibleVariableOverride]
    """If specified provides a callback providing the updated chart width and
    height values."""

    initialDimension: DimensionRequired
    """The initial dimensions of the container. This is useful for pre-rendering
    where the container size cannot be determined automatically."""


@ps.react_component("ResponsiveContainer", "recharts")
def ResponsiveContainer(
    *children: ps.Child,
    key: Optional[str] = None,
    **props: Unpack[ResponsiveContainerProps],
): ...


SymbolType = Literal["circle", "cross", "diamond", "square", "star", "triangle", "wye"]
LegendType = Literal[
    "circle",
    "cross",
    "diamond",
    "line",
    "plainline",
    "rect",
    "square",
    "star",
    "triangle",
    "wye",
    "none",
]


@dataclass
class LegendData(Generic[T]):
    strokeDasharray: Optional[float | str] = None
    value: Optional[T] = None


@dataclass
class LegendPayload(Generic[T]):
    """This is the text that will be displayed in the legend in the DOM.
    If undefined, the text will not be displayed, so the icon will be rendered without text."""

    value: str | None
    type: Optional[LegendType] = None
    color: Optional[str] = None
    payload: Optional[LegendData[T]] = None
    # formatter?: Formatter;
    inactive: Optional[bool] = None
    # legendIcon?: ReactElement<SVGElement>;
    dataKey: Optional[DataKey[T]] = None


class LegendProps(ps.HTMLProps, Generic[T], total=False):
    width: float
    """The width of legend."""

    height: float
    """The height of legend."""

    layout: Literal["horizontal", "vertical"]
    """The layout of legend items. One of: 'horizontal', 'vertical'. Default: 'horizontal'"""

    align: Literal["left", "center", "right"]
    """The alignment of legend. One of: 'left', 'center', 'right'. Default: 'center'"""

    verticalAlign: Literal["top", "middle", "bottom"]
    """The vertical alignment of legend. One of: 'top', 'middle', 'bottom'. Default: 'bottom'"""

    iconSize: float
    """The size of icon in each legend item. Default: 14"""

    iconType: Literal[
        "line",
        "plainline",
        "square",
        "rect",
        "circle",
        "cross",
        "diamond",
        "star",
        "triangle",
        "wye",
    ]
    """The type of icon in each legend item. One of: 'line', 'plainline', 'square', 'rect', 'circle', 'cross', 'diamond', 'star', 'triangle', 'wye'"""

    payload: list[LegendPayload[T]]
    """The source data of the content to be displayed in the legend. Default: []"""

    # content: NotRequired[ps.Child]
    """React element or function to render custom legend content"""

    # formatter: Callable[[str, Any, int], Any]
    """The formatter function of each text in legend"""

    wrapperStyle: ps.CSSProperties
    """The style of legend container"""

    onClick: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of click on the items"""

    onMouseDown: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mousedown on the items"""

    onMouseUp: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mouseup on the items"""

    onMouseMove: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mousemove on the items"""

    onMouseOver: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mouseover on the items"""

    onMouseOut: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mouseout on the items"""

    onMouseEnter: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mouseenter on the items"""

    onMouseLeave: ps.EventHandler2[LegendPayload[T], int]  # pyright: ignore[reportIncompatibleVariableOverride]
    """The customized event handler of mouseleave on the items"""


@ps.react_component("Legend", "recharts")
def Legend(
    key: Optional[str] = None,
    **props: Unpack[LegendProps],
): ...


AnimationEasing = Literal["ease", "ease-in", "ease-out", "ease-in-out", "linear"]


# TODO: better payload typing
# TODO: better cursor definitions
class TooltipProps(TypedDict, total=False):
    separator: str
    """The separator between name and value. Default: ' : '"""

    offset: int
    """The offset size between the position of tooltip and the active position. Default: 10"""

    filterNull: bool
    """When an item of the payload has value null or undefined, this item won't be displayed. Default: True"""

    itemStyle: ps.CSSProperties
    """The style of default tooltip content item which is a li element. Default: {}"""

    wrapperStyle: ps.CSSProperties
    """The style of tooltip wrapper which is a dom element. Default: {}"""

    contentStyle: ps.CSSProperties
    """The style of tooltip content which is a dom element. Default: {}"""

    labelStyle: ps.CSSProperties
    """The style of default tooltip label which is a p element. Default: {}"""

    cursor: Union[bool, dict, ps.Element]
    """If set false, no cursor will be drawn when tooltip is active. If set a
    object, the option is the configuration of cursor. If set a React element,
    the option is the custom react element of drawing cursor. Default: True"""

    # viewBox: dict
    """The box of viewing area, which has the shape of {x: someVal, y: someVal,
    width: someVal, height: someVal}, usually calculated internally."""

    allowEscapeViewBox: Dimension
    """This option allows the tooltip to extend beyond the viewBox of the chart itself. Default: { x: False, y: False }"""

    active: bool
    """If set true, the tooltip is displayed. If set false, the tooltip is hidden, usually calculated internally. Default: False"""

    position: dict
    """If this field is set, the tooltip position will be fixed and will not move anymore."""

    coordinate: dict
    """The coordinate of tooltip position, usually calculated internally. Default: { x: 0, y: 0 }"""

    payload: list
    """The source data of the content to be displayed in the tooltip, always calculated internally and cannot be user set. Default: []"""

    label: Union[str, int]
    """The label value which is active now, usually calculated internally."""

    # content: Union[ps.Child, Callable]
    """If set a React element, the option is the custom react element of rendering tooltip. If set a function, the function will be called to render tooltip content."""

    # formatter: Callable[[Any, str, Any], Union[str, list[str]]]
    """The formatter function of value in tooltip."""

    # labelFormatter: Callable[[Any], Any]
    """The formatter function of label in tooltip."""

    # itemSorter: Callable[[Any], int]
    """Sort function of payload. Default: lambda: -1"""

    shared: bool
    """If true, tooltip will appear on top of all bars on an axis tick. If
    false, tooltip will appear on individual bars. Currently only supported in
    BarChart and RadialBarChart. Default: True"""

    isAnimationActive: bool
    """If set false, animation of tooltip will be disabled. Default: True in CSR, False in SSR"""

    animationDuration: int
    """Specifies the duration of animation, the unit of this option is ms. Default: 1500"""

    animationEasing: AnimationEasing
    """The type of easing function. Default: 'ease'"""

    trigger: Literal["click", "hover"]
    """If 'hover' then the Tooltip shows on mouse enter and hides on mouse leave.
    If 'click' then the Tooltip shows after clicking and stays active. 
    Default 'hover'"""

    axisId: str | int
    """Tooltip always attaches itself to the "Tooltip" axis. Which axis is it? Depends on the layout:
    - horizontal layout -> X axis
    - vertical layout -> Y axis
    - radial layout -> radial axis
    - centric layout -> angle axis

    Tooltip will use the default axis for the layout, unless you specify an axisId."""


@ps.react_component("Tooltip", "recharts")
def Tooltip(
    key: Optional[str] = None,
    **props: Unpack[TooltipProps],
): ...


# TODO: Cell

TextAnchor = Literal["start", "middle", "end", "inherit"]
VerticalAnchor = Literal["start", "middle", "end"]


class TextProps(TypedDict, total=False):
    scaleToFit: bool
    """Scale the text to fit the width or not. Default: False"""

    angle: float
    """The rotate angle of Text."""

    width: float
    """The width of Text. When the width is specified to be a number, the text will warp auto by calculating the width of text."""

    textAnchor: TextAnchor
    """Text anchor. Default: 'start'"""

    verticalAnchor: VerticalAnchor
    """Vertical anchor. Default: 'end'"""


@ps.react_component("Text", "recharts")
def Text(
    key: Optional[str] = None,
    **props: Unpack[TextProps],
): ...


LabelPosition = Literal[
    "top",
    "left",
    "right",
    "bottom",
    "inside",
    "outside",
    "insideLeft",
    "insideRight",
    "insideTop",
    "insideBottom",
    "insideTopLeft",
    "insideBottomLeft",
    "insideTopRight",
    "insideBottomRight",
    "insideStart",
    "insideEnd",
    "end",
    "center",
    "centerTop",
    "centerBottom",
    "middle",
]


class LabelProps(HTMLSVGProps, Generic[T], total=False):
    viewBox: ViewBox  # pyright: ignore[reportIncompatibleVariableOverride]
    "The box of viewing area, which has the shape of {x: someVal, y: someVal, width: someVal, height: someVal}, usually calculated internally."
    # parentViewBox: ViewBox
    value: int | float | str
    "The value of label, which can be specified by this props or the children of <Label />"
    offset: float  # pyright: ignore[reportIncompatibleVariableOverride]
    'The offset to the specified "position"'
    position: LabelPosition | Dimension
    "The position of label relative to the view box. See the docs for the meaning of each option: https://recharts.org/en-US/api/Label"
    textBreakAll: bool
    angle: float
    index: int
    # content?: ContentType; # ContentType = ReactElement | ((props: Props) => ReactNode)
    # formatter?: (label: React.ReactNode) => React.ReactNode;
    # children?: ReactNode;
    # labelRef?: React.RefObject<Element>;


@ps.react_component("Label", "recharts")
def Label(
    key: Optional[str] = None,
    **props: Unpack[LabelProps],
): ...


class LabelListProps(ps.HTMLSVGProps, Generic[T], total=False):
    id: str
    "The unique id of this component, which will be used to generate unique clip path id internally. This props is suggested to be set in SSR."

    data: list[T]
    "The data input to the charts."

    valueAccessor: ps.JsFunction[[T, int], str | int]
    "The accessor function to get the value of each label: (entry: T, idx: int) => str | int"

    clockwise: bool
    "The parameter to calculate the view box of label in radial charts. Default: False."

    dataKey: DataKey[T]
    "The key of a group of label values in data."

    position: LabelPosition
    "The position of each label relative to it view box。"

    offset: int  # pyright: ignore[reportIncompatibleVariableOverride]
    'The offset to the specified "position". Default: 5'

    angle: float

    textBreakAll: bool

    formatter: ps.JsFunction[[ps.Element], ps.Element]

    content: ps.Element | ps.JsFunction[[ps.Element], ps.Element]
    """If set a React element, the option is the customized react element of rendering each label. If set a function, the function will be called to render each label content.
Examples:
<LabelList content={<CustomizedLabel external={external} />} />
<LabelList content={renderLabel} />"""


@ps.react_component("LabelList", "recharts")
def LabelList(
    key: Optional[str] = None,
    **props: Unpack[LabelListProps],
): ...


# TODO: Customizezd

__all__ = [
    "ResponsiveContainer",
    "ResponsiveContainerProps",
    "Legend",
    "LegendProps",
    "LegendPayload",
    "TooltipProps",
    "Tooltip",
    "Label",
    "LabelProps",
    "LabelList",
    "LabelListProps",
]
