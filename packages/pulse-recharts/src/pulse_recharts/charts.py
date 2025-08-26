from typing import Generic, Optional, TypeVar, TypedDict, Unpack
import pulse as ps
from .common import CartesianLayout, DataKey, Margin, StackOffsetType, SyncMethod


T = TypeVar("T")


class CartesianChartProps(TypedDict, Generic[T], total=False):
    accessibilityLayer: bool
    barCategoryGap: float | str
    barGap: float | str
    barSize: float | str
    className: str
    compact: bool
    data: list[T]
    dataKey: DataKey[T]
    desc: str
    height: float
    id: str
    layout: CartesianLayout
    margin: Margin
    maxBarSize: float
    reverseStackOrder: bool
    role: str
    stackOffset: StackOffsetType
    style: ps.CssStyle
    syncId: float | str
    syncMethod: SyncMethod
    tabIndex: float
    throttleDelay: float
    title: str
    width: float


# SVG <svg> element
class LineChartProps(CartesianChartProps, ps.HTMLSVGProps): ...


@ps.react_component("LineChart", "recharts")
def LineChart(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[LineChartProps]
): ...
