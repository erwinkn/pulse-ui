from typing import Literal, Optional, TypedDict, Unpack, NotRequired
import pulse as ps


class ResponsiveContainerProps(TypedDict, total=False):
    aspect: float
    """width / height. If specified, the height will be calculated by width / aspect."""

    widthPercentage: float | str
    """The percentage value of the chart's width or a fixed width. Default: '100%'"""

    heightPercentage: float | str
    """The percentage value of the chart's width or a fixed height. Default: '100%'"""

    minWidth: float
    """The minimum width of the container."""

    minHeight: float
    """The minimum height of the container."""

    debounce: int
    """If specified a positive number, debounced function will be used to handle the resize event. Default: 0"""

    onResize: ps.EventHandler[float, float]
    """If specified provides a callback providing the updated chart width and height values."""


@ps.react_component("ResponsiveContainer", "recharts")
def ResponsiveContainer(
    *children: ps.Child,
    key: Optional[str] = None,
    **props: Unpack[ResponsiveContainerProps],
): ...


class LegendProps(TypedDict, total=False):
    width: float
    """The width of legend."""

    height: float 
    """The height of legend."""

    layout: Literal['horizontal', 'vertical']
    """The layout of legend items. One of: 'horizontal', 'vertical'. Default: 'horizontal'"""

    align: Literal['left', 'center', 'right']
    """The alignment of legend. One of: 'left', 'center', 'right'. Default: 'center'"""

    verticalAlign: Literal['top', 'middle', 'bottom']
    """The vertical alignment of legend. One of: 'top', 'middle', 'bottom'. Default: 'bottom'"""

    iconSize: float
    """The size of icon in each legend item. Default: 14"""

    iconType: Literal['line', 'plainline', 'square', 'rect', 'circle', 'cross', 'diamond', 'star', 'triangle', 'wye']
    """The type of icon in each legend item. One of: 'line', 'plainline', 'square', 'rect', 'circle', 'cross', 'diamond', 'star', 'triangle', 'wye'"""

    payload: list
    """The source data of the content to be displayed in the legend. Default: []"""

    # content: NotRequired[ps.Child]
    """React element or function to render custom legend content"""

    # formatter: Callable[[str, Any, int], Any]
    """The formatter function of each text in legend"""

    wrapperStyle: dict
    """The style of legend container"""

    onClick: ps.EventHandler
    """The customized event handler of click on the items"""

    onMouseDown: ps.EventHandler
    """The customized event handler of mousedown on the items"""

    onMouseUp: ps.EventHandler
    """The customized event handler of mouseup on the items"""

    onMouseMove: ps.EventHandler
    """The customized event handler of mousemove on the items"""

    onMouseOver: ps.EventHandler
    """The customized event handler of mouseover on the items"""

    onMouseOut: ps.EventHandler
    """The customized event handler of mouseout on the items"""

    onMouseEnter: ps.EventHandler
    """The customized event handler of mouseenter on the items"""

    onMouseLeave: ps.EventHandler
    """The customized event handler of mouseleave on the items"""


@ps.react_component("Legend", "recharts")
def Legend(
    key: Optional[str] = None,
    **props: Unpack[LegendProps],
): ...
