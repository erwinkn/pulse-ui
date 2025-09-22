from __future__ import annotations

from typing import Sequence, TypedDict, TypeVar

import pulse as ps

from .theme import (
    MantineLineHeight,
    MantineSpacing,
    MantineTheme,
)
from .types import (
    MantineBreakpoint,
    MantineColor,
    MantineFontFamily,
    MantineFontSize,
    MantineFontStyle,
    MantinePosition,
    MantineTextAlign,
    MantineTextDecoration,
    MantineTextTransform,
)

T = TypeVar("T")

StyleProp = T | dict[str | MantineBreakpoint, T]
"""Wrapper for the type of Mantine style props like `m` (margin) or `p`
(padding). Not to be confused with MantineStyleProp, which is used for the
`style` prop."""

T = TypeVar("T")
Props = TypeVar("Props")
Ctx = TypeVar("Ctx")
StyleFn = ps.JsFunction[[MantineTheme, Props, Ctx], T]
"(theme: MantineTheme, props, ctx) => styles payload"

MantineStyle = ps.CSSProperties | ps.JsFunction[[MantineTheme], ps.CSSProperties]
MantineStyleProp = (
    MantineStyle | Sequence[MantineStyle] | Sequence["MantineStyleProp"] | None
)
"""Refers to the `style` prop of Mantine components. Not to be confused with
`StyleProp`, which is used for the type of style props `m` (margin) or `p`
(padding)."""


# The actual types are even more wicked than this (ex: CssVars can be an array
# of CssVars so infinite recursion is possible), but we try to provide the most
# pragmatic version
CSSVariablesDict = dict[str, str] | ps.JsFunction[[MantineTheme], dict[str, str]]
CSSVariables = CSSVariablesDict | Sequence[CSSVariablesDict]


class MantineStyleProps(TypedDict, total=False):
    m: StyleProp[MantineSpacing]
    """Margin, theme key: theme.spacing"""
    my: StyleProp[MantineSpacing]
    """MarginBlock, theme key: theme.spacing"""
    mx: StyleProp[MantineSpacing]
    """MarginInline, theme key: theme.spacing"""
    mt: StyleProp[MantineSpacing]
    """MarginTop, theme key: theme.spacing"""
    mb: StyleProp[MantineSpacing]
    """MarginBottom, theme key: theme.spacing"""
    ms: StyleProp[MantineSpacing]
    """MarginInlineStart, theme key: theme.spacing"""
    me: StyleProp[MantineSpacing]
    """MarginInlineEnd, theme key: theme.spacing"""
    ml: StyleProp[MantineSpacing]
    """MarginLeft, theme key: theme.spacing"""
    mr: StyleProp[MantineSpacing]
    """MarginRight, theme key: theme.spacing"""
    p: StyleProp[MantineSpacing]
    """Padding, theme key: theme.spacing"""
    py: StyleProp[MantineSpacing]
    """PaddingBlock, theme key: theme.spacing"""
    px: StyleProp[MantineSpacing]
    """PaddingInline, theme key: theme.spacing"""
    pt: StyleProp[MantineSpacing]
    """PaddingTop, theme key: theme.spacing"""
    pb: StyleProp[MantineSpacing]
    """PaddingBottom, theme key: theme.spacing"""
    ps: StyleProp[MantineSpacing]
    """PaddingInlineStart, theme key: theme.spacing"""
    pe: StyleProp[MantineSpacing]
    """PaddingInlineEnd, theme key: theme.spacing"""
    pl: StyleProp[MantineSpacing]
    """PaddingLeft, theme key: theme.spacing"""
    pr: StyleProp[MantineSpacing]
    """PaddingRight, theme key: theme.spacing"""
    bd: StyleProp[str]
    """Border"""
    bdrs: StyleProp[MantineSpacing]
    """BorderRadius, theme key: theme.radius"""
    bg: StyleProp[MantineColor]
    """Background, theme key: theme.colors"""
    c: StyleProp[MantineColor]
    """Color"""
    opacity: StyleProp[str | float]
    """Opacity"""
    ff: StyleProp[MantineFontFamily | str]
    """FontFamily"""
    fz: StyleProp[MantineFontSize | str | float]
    """FontSize, theme key: theme.fontSizes"""
    fw: StyleProp[str | float]
    """FontWeight"""
    lts: StyleProp[str | float]
    """LetterSpacing"""
    ta: StyleProp[MantineTextAlign]
    """TextAlign"""
    lh: StyleProp[MantineLineHeight | str | float]
    """LineHeight, theme key: lineHeights"""
    fs: StyleProp[MantineFontStyle]
    """FontStyle"""
    tt: StyleProp[MantineTextTransform]
    """TextTransform"""
    td: StyleProp[MantineTextDecoration]
    """TextDecoration"""
    w: StyleProp[str | float]
    """Width, theme key: theme.spacing"""
    miw: StyleProp[str | float]
    """MinWidth, theme key: theme.spacing"""
    maw: StyleProp[str | float]
    """MaxWidth, theme key: theme.spacing"""
    h: StyleProp[str | float]
    """Height, theme key: theme.spacing"""
    mih: StyleProp[str | float]
    """MinHeight, theme key: theme.spacing"""
    mah: StyleProp[str | float]
    """MaxHeight, theme key: theme.spacing"""
    bgsz: StyleProp[str]
    """BackgroundSize"""
    bgp: StyleProp[str]
    """BackgroundPosition"""
    bgr: StyleProp[str]
    """BackgroundRepeat"""
    bga: StyleProp[str]
    """BackgroundAttachment"""
    pos: StyleProp[MantinePosition]
    """Position"""
    top: StyleProp[str | float]
    """Top"""
    left: StyleProp[str | float]
    """Left"""
    bottom: StyleProp[str | float]
    """Bottom"""
    right: StyleProp[str | float]
    """Right"""
    inset: StyleProp[str | float]
    """Inset"""
    display: StyleProp[str]
    """Display"""
    flex: StyleProp[str | float]
    """Flex"""
