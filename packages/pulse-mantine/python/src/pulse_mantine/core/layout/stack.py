from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, Unpack
import pulse as ps
from ..styles import StyleFn, StyleProp
from ..theme import MantineSpacing
from ..box import BoxProps

StackStylesNames = Literal["root"]
StackAttributes = dict[StackStylesNames, dict[str, Any]]
StackStyles = dict[StackStylesNames, ps.CSSProperties]
StackClassNames = dict[StackStylesNames, str]


class StackCSSVariables(TypedDict, total=False):
    root: dict[Literal["--stack-gap", "--stack-align", "--stack-justify"], str]


class StackProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
    gap: StyleProp[MantineSpacing]
    """Key of `theme.spacing` or any valid CSS value to set `gap` property, numbers are converted to rem @default `'md'`"""
    align: str
    """Controls `align-items` CSS property @default `'stretch'`"""
    justify: str
    """Controls `justify-content` CSS property @default `'flex-start'`"""

    # Styles API props
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: StackClassNames | StyleFn[StackProps, Any, StackClassNames]
    """Additional class names passed to elements"""
    styles: StackStyles | StyleFn[StackProps, Any, StackStyles]
    """Additional styles passed to elements"""
    vars: StackCSSVariables
    """CSS variables for the component"""
    attributes: StackAttributes
    """Additional attributes passed to elements"""


@ps.react_component("Stack", "@mantine/core")
def Stack(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[StackProps]
): ...
