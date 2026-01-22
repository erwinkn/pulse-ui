from dataclasses import dataclass
from typing import (
	Any,
	Generic,
	Literal,
	TypedDict,
	TypeVar,
	Unpack,
)

import pulse as ps
from pulse.dom.elements import GenericHTMLElement
from pulse.dom.props import HTMLSVGProps

from .common import Coordinate, DataKey

T = TypeVar("T")


class DimensionRequired(TypedDict):
	width: float
	height: float


class Dimension(TypedDict, total=False):
	width: float | None
	height: float | None


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


class AllowInDimension(TypedDict, total=False):
	x: bool
	y: bool


class SurfaceProps(TypedDict, total=False):
	width: float | str
	height: float | str
	viewBox: str
	className: str
	style: ps.CSSProperties


@ps.react_component(ps.Import("Surface", "recharts"))
def Surface(
	*children: ps.Node,
	key: str | None = None,
	**props: Unpack[SurfaceProps],
): ...


class LayerProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	className: str


@ps.react_component(ps.Import("Layer", "recharts"))
def Layer(
	*children: ps.Node,
	key: str | None = None,
	**props: Unpack[LayerProps],
): ...


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


@ps.react_component(ps.Import("ResponsiveContainer", "recharts"))
def ResponsiveContainer(
	*children: ps.Node,
	key: str | None = None,
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
	strokeDasharray: float | str | None = None
	value: T | None = None


@dataclass
class LegendPayload(Generic[T]):
	"""This is the text that will be displayed in the legend in the DOM.
	If undefined, the text will not be displayed, so the icon will be rendered without text."""

	value: str | None
	type: LegendType | None = None
	color: str | None = None
	payload: LegendData[T] | None = None
	# formatter?: Formatter;
	inactive: bool | None = None
	# legendIcon?: ReactElement<SVGElement>;
	dataKey: DataKey[T] | None = None


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

	# content: NotRequired[ps.Node]
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


@ps.react_component(ps.Import("Legend", "recharts"))
def Legend(
	key: str | None = None,
	**props: Unpack[LegendProps[Any]],
): ...


class DefaultLegendContentProps(TypedDict, Generic[T], total=False):
	payload: list[LegendPayload[T]]
	layout: Literal["horizontal", "vertical"]
	align: Literal["left", "center", "right"]
	verticalAlign: Literal["top", "middle", "bottom"]
	iconSize: float
	iconType: LegendType
	wrapperStyle: ps.CSSProperties


@ps.react_component(ps.Import("DefaultLegendContent", "recharts"))
def DefaultLegendContent(
	key: str | None = None,
	**props: Unpack[DefaultLegendContentProps[Any]],
): ...


AnimationEasing = Literal["ease", "ease-in", "ease-out", "ease-in-out", "linear"]


# TODO: better payload typing
# TODO: better cursor definitions
class TooltipProps(TypedDict, total=False):
	separator: str
	"""The separator between name and value. Default: ' : '"""

	offset: int | Coordinate
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

	cursor: bool | dict[str, Any] | ps.Element
	"""If set false, no cursor will be drawn when tooltip is active. If set a
    object, the option is the configuration of cursor. If set a React element,
    the option is the custom react element of drawing cursor. Default: True"""

	# viewBox: dict
	"""The box of viewing area, which has the shape of {x: someVal, y: someVal,
    width: someVal, height: someVal}, usually calculated internally."""

	allowEscapeViewBox: AllowInDimension
	"""This option allows the tooltip to extend beyond the viewBox of the chart itself. Default: { x: False, y: False }"""

	active: bool
	"""If set true, the tooltip is displayed. If set false, the tooltip is hidden, usually calculated internally. Default: False"""

	defaultIndex: int | str | None
	"""If set, tooltip becomes active before user interaction."""

	position: Coordinate | dict[str, Any]
	"""If this field is set, the tooltip position will be fixed and will not move anymore."""

	coordinate: Coordinate | dict[str, Any]
	"""The coordinate of tooltip position, usually calculated internally. Default: { x: 0, y: 0 }"""

	payload: list[Any]
	"""The source data of the content to be displayed in the tooltip, always calculated internally and cannot be user set. Default: []"""

	label: str | int
	"""The label value which is active now, usually calculated internally."""

	content: ps.Element | ps.JsFunction[Any, ps.Element]
	"""If set a React element, the option is the custom react element of rendering tooltip. If set a function, the function will be called to render tooltip content."""

	formatter: ps.JsFunction[Any, Any]
	"""The formatter function of value in tooltip."""

	labelFormatter: ps.JsFunction[Any, Any]
	"""The formatter function of label in tooltip."""

	itemSorter: Literal["dataKey", "value", "name"] | ps.JsFunction[Any, Any]
	"""Sort function of payload. Default: lambda: -1"""

	shared: bool
	"""If true, tooltip will appear on top of all bars on an axis tick. If
    false, tooltip will appear on individual bars. Currently only supported in
    BarChart and RadialBarChart. Default: True"""

	includeHidden: bool
	"""If true, tooltip will display hidden series. Default: False"""

	isAnimationActive: bool | Literal["auto"]
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

	payloadUniqBy: Any
	reverseDirection: AllowInDimension
	portal: Any
	useTranslate3d: bool


@ps.react_component(ps.Import("Tooltip", "recharts"))
def Tooltip(
	key: str | None = None,
	**props: Unpack[TooltipProps],
): ...


class DefaultTooltipContentProps(TypedDict, total=False):
	separator: str
	wrapperStyle: ps.CSSProperties
	contentStyle: ps.CSSProperties
	labelStyle: ps.CSSProperties
	itemStyle: ps.CSSProperties
	payload: list[Any]
	label: str | int
	formatter: ps.JsFunction[Any, Any]
	labelFormatter: ps.JsFunction[Any, Any]


@ps.react_component(ps.Import("DefaultTooltipContent", "recharts"))
def DefaultTooltipContent(
	key: str | None = None,
	**props: Unpack[DefaultTooltipContentProps],
): ...


class CellProps(TypedDict, total=False):
	fill: str
	stroke: str
	strokeWidth: float
	className: str
	name: str | int
	value: str | int | float
	payload: Any


@ps.react_component(ps.Import("Cell", "recharts"))
def Cell(key: str | None = None, **props: Unpack[CellProps]): ...


class CustomizedProps(TypedDict, total=False):
	component: ps.Element | ps.JsFunction[Any, ps.Element]


@ps.react_component(ps.Import("Customized", "recharts"))
def Customized(key: str | None = None, **props: Unpack[CustomizedProps]): ...


class ZIndexLayerProps(TypedDict, total=False):
	zIndex: int | None


@ps.react_component(ps.Import("ZIndexLayer", "recharts"))
def ZIndexLayer(
	*children: ps.Node,
	key: str | None = None,
	**props: Unpack[ZIndexLayerProps],
): ...


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


@ps.react_component(ps.Import("Text", "recharts"))
def Text(
	key: str | None = None,
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


class LabelProps(HTMLSVGProps[GenericHTMLElement], Generic[T], total=False):
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


@ps.react_component(ps.Import("Label", "recharts"))
def Label(
	key: str | None = None,
	**props: Unpack[LabelProps[Any]],
): ...


class LabelListProps(ps.HTMLSVGProps[GenericHTMLElement], Generic[T], total=False):
	id: str
	"The unique id of this component, which will be used to generate unique clip path id internally. This props is suggested to be set in SSR."

	data: list[T]
	"The data input to the charts."

	valueAccessor: ps.JsFunction[T, int, str | int]
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

	formatter: ps.JsFunction[ps.Element, ps.Element]

	content: ps.Element | ps.JsFunction[ps.Element, ps.Element]
	"""If set a React element, the option is the customized react element of rendering each label. If set a function, the function will be called to render each label content.
Examples:
<LabelList content={<CustomizedLabel external={external} />} />
<LabelList content={renderLabel} />"""


@ps.react_component(ps.Import("LabelList", "recharts"))
def LabelList(
	key: str | None = None,
	**props: Unpack[LabelListProps[Any]],
): ...


# TODO: Customizezd

__all__ = [
	"Surface",
	"SurfaceProps",
	"Layer",
	"LayerProps",
	"ResponsiveContainer",
	"ResponsiveContainerProps",
	"Legend",
	"LegendProps",
	"LegendPayload",
	"DefaultLegendContent",
	"DefaultLegendContentProps",
	"TooltipProps",
	"Tooltip",
	"DefaultTooltipContent",
	"DefaultTooltipContentProps",
	"Cell",
	"CellProps",
	"Customized",
	"CustomizedProps",
	"ZIndexLayer",
	"ZIndexLayerProps",
	"Text",
	"TextProps",
	"Label",
	"LabelProps",
	"LabelList",
	"LabelListProps",
]
