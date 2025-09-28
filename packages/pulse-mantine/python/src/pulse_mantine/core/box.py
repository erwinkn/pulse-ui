from typing import Any, Optional, Sequence, Unpack
import pulse as ps
from .base import MantineComponentProps
from .types import MantineBreakpoint
from .styles import MantineStyleProps, CSSVariables, MantineStyleProp

Mod = dict[str, Any] | str
BoxMod = Mod | Sequence[Mod] | Sequence["BoxMod"]


class BoxProps(MantineStyleProps, total=False):
    className: str
    "Class added to the root element, if applicable"
    style: MantineStyleProp
    "Inline style added to root component element, can subscribe to theme defined on MantineProvider"
    __vars: CSSVariables
    "CSS variables defined on root component element"
    __size: str
    "`size` property passed down the HTML element"
    hiddenFrom: MantineBreakpoint
    "Breakpoint above which the component is hidden with `display: none`"
    visibleFrom: MantineBreakpoint
    "Breakpoint below which the component is hidden with `display: none`"
    lightHidden: bool
    "Determines whether component should be hidden in light color scheme with `display: none`"
    darkHidden: bool
    "Determines whether component should be hidden in dark color scheme with `display: none`"
    mod: BoxMod
    "Element modifiers transformed into `data-` attributes, for example, `{ 'data-size': 'xl' }`, falsy values are removed"


class BoxComponentProps(BoxProps, MantineComponentProps, total=False):
    variant: str
    "Variant passed from parent component, sets `data-variant`"
    size: str | float
    "Size passed from parent component, sets `data-size` if value is not number like"


@ps.react_component("Box", "@mantine/core")
def Box(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[BoxComponentProps]
): ...
