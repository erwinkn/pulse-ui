from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, Unpack
import pulse as ps
from ..styles import StyleFn, StyleProp
from ..theme import MantineSpacing
from ..box import BoxProps

FlexStylesNames = Literal["root"]
FlexAttributes = dict[FlexStylesNames, dict[str, Any]]
FlexStyles = dict[FlexStylesNames, ps.CSSProperties]
FlexClassNames = dict[FlexStylesNames, str]


class FlexProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
    gap: StyleProp[MantineSpacing]
    """gap CSS property"""
    rowGap: StyleProp[MantineSpacing]
    """row-gap CSS property"""
    columnGap: StyleProp[MantineSpacing]
    """column-gap CSS property"""
    align: StyleProp[str]
    """align-items CSS property"""
    justify: StyleProp[str]
    """justify-content CSS property"""
    wrap: StyleProp[str]
    """flex-wrap CSS property"""
    direction: StyleProp[str]
    """flex-direction CSS property"""

    # Styles API props
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: FlexClassNames | StyleFn[FlexProps, Any, FlexClassNames]
    """Additional class names passed to elements"""
    styles: FlexStyles | StyleFn[FlexProps, Any, FlexStyles]
    """Additional styles passed to elements"""
    # no vars
    attributes: FlexAttributes
    """Additional attributes passed to elements"""


@ps.react_component("Flex", "@mantine/core")
def Flex(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[FlexProps]
): ...
