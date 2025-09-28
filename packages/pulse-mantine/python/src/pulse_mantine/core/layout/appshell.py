from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn
from ..theme import MantineSpacing
from ..types import MantineBreakpoint, MantineSize


class AppShellCompoundProps(TypedDict, total=False):
    withBorder: bool
    "If set, component haves a border, overrides `withBorder` prop on `AppShell` component"
    zIndex: float | str
    "Sets `z-index`. Inherited from the `AppShell` by default."


AppShellSize = float | str
AppShellResponsiveSize = dict[MantineSize | str, AppShellSize]

AppShellLayout = Literal["default", "alt"]

TransitionTimingFunction = Literal[
    "linear", "ease", "ease-in", "ease-out", "ease-in-out", "step-start", "step-end"
]


class AppShellCollapsed(TypedDict, total=False):
    desktop: bool
    """Desktop collapsed state"""
    mobile: bool
    """Mobile collapsed state"""


class AppShellNavbarConfiguration(TypedDict, total=False):
    width: AppShellSize | AppShellResponsiveSize
    """Width of the navbar, can be a fixed size or responsive sizes"""
    breakpoint: MantineBreakpoint | float
    """Breakpoint at which the navbar collapses"""
    collapsed: AppShellCollapsed
    """Collapsed state configuration for desktop and mobile"""


class AppShellAsideConfiguration(TypedDict, total=False):
    width: AppShellSize | AppShellResponsiveSize
    """Width of the aside, can be a fixed size or responsive sizes"""
    breakpoint: MantineBreakpoint | float
    """Breakpoint at which the aside collapses"""
    collapsed: AppShellCollapsed
    """Collapsed state configuration for desktop and mobile"""


class AppShellHeaderConfiguration(TypedDict, total=False):
    height: AppShellSize | AppShellResponsiveSize
    """Height of the header, can be a fixed size or responsive sizes"""
    collapsed: bool
    """Whether the header is collapsed"""
    offset: bool
    """Whether to offset scrollbars for the header"""


class AppShellFooterConfiguration(TypedDict, total=False):
    height: AppShellSize | AppShellResponsiveSize
    """Height of the footer, can be a fixed size or responsive sizes"""
    collapsed: bool
    """Whether the footer is collapsed"""
    offset: bool
    """Whether to offset scrollbars for the footer"""


AppShellRootCSSVariables = Literal[
    "--app-shell-transition-duration", "--app-shell-transition-timing-function"
]
AppShellStylesNames = Literal[
    "aside", "footer", "header", "main", "navbar", "root", "section"
]
AppShellAttributes = dict[AppShellStylesNames, dict[str, Any]]
AppShellStyles = dict[AppShellStylesNames, ps.CSSProperties]
AppShellClassNames = dict[AppShellStylesNames, str]


class AppShellCSSVariables(TypedDict, total=False):
    root: dict[AppShellRootCSSVariables, str]


class AppShellProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
    withBorder: bool
    """If set, the associated components have a border, defaults to `true`"""
    padding: MantineSpacing | AppShellResponsiveSize
    """Padding of the main section. Important: use `padding` prop instead of `p`, defaults to `0`"""
    navbar: AppShellNavbarConfiguration
    """Navbar configuration, controls width, breakpoints and collapsed state. Required if you use `Navbar` component"""
    aside: AppShellAsideConfiguration
    """Aside configuration, controls width, breakpoints and collapsed state. Required if you use `Aside` component"""
    header: AppShellHeaderConfiguration
    """Header configuration, controls height, offset and collapsed state. Required if you use `Header` component"""
    footer: AppShellFooterConfiguration
    """Footer configuration, controls height, offset and collapsed state. Required if you use `Footer` component"""
    transitionDuration: float
    """Duration of all transitions in ms, defaults to `200`"""
    transitionTimingFunction: TransitionTimingFunction
    """Timing function of all transitions, defaults to `ease`"""
    zIndex: float | str
    """Z-index of all associated elements, defaults to `100`"""
    layout: AppShellLayout
    """Determines how `Navbar`/`Aside` are arranged relative to `Header`/`Footer`"""
    disabled: bool
    """If set, `Navbar`, `Aside`, `Header` and `Footer` components are hidden"""
    offsetScrollbars: bool
    """If set, `Header` and `Footer` components include styles to offset scrollbars. Based on `react-remove-scroll`, defaults to `true` for `layout="default"`, `false` for `layout="alt"`"""

    # Styles API props
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: AppShellClassNames | StyleFn[AppShellProps, Any, AppShellClassNames]
    """Additional class names passed to elements"""
    styles: AppShellStyles | StyleFn[AppShellProps, Any, AppShellStyles]
    """Additional styles passed to elements"""
    vars: StyleFn[AppShellProps, Any, AppShellCSSVariables]
    """CSS variables for the component"""
    attributes: AppShellAttributes
    """Additional attributes passed to elements"""


@ps.react_component("AppShell", "@mantine/core")
def AppShell(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellProps]
): ...


AppShellAsideStylesNames = Literal["aside"]
AppShellAsideAttributes = dict[AppShellAsideStylesNames, dict[str, Any]]
AppShellAsideStyles = dict[AppShellAsideStylesNames, ps.CSSProperties]
AppShellAsideClassNames = dict[AppShellAsideStylesNames, str]


class AppShellAsideProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLAsideProps, BoxProps, AppShellCompoundProps, total=False
):
    # Styles API
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AppShellAsideClassNames
        | StyleFn[AppShellAsideProps, Any, AppShellAsideClassNames]
    )
    """Additional class names passed to elements"""
    styles: AppShellAsideStyles | StyleFn[AppShellAsideProps, Any, AppShellAsideStyles]
    """Additional styles passed to elements"""
    # no vars
    attributes: AppShellAsideAttributes
    """Additional attributes passed to elements"""


@ps.react_component("AppShell", "@mantine/core", prop="Aside")
def AppShellAside(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellAsideProps]
): ...


AppShellHeaderStylesNames = Literal["header"]
AppShellHeaderAttributes = dict[AppShellHeaderStylesNames, dict[str, Any]]
AppShellHeaderStyles = dict[AppShellHeaderStylesNames, ps.CSSProperties]
AppShellHeaderClassNames = dict[AppShellHeaderStylesNames, str]


class AppShellHeaderProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLHeaderProps, BoxProps, AppShellCompoundProps, total=False
):
    # Styles API
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AppShellHeaderClassNames
        | StyleFn[AppShellHeaderProps, Any, AppShellHeaderClassNames]
    )
    """Additional class names passed to elements"""
    styles: (
        AppShellHeaderStyles | StyleFn[AppShellHeaderProps, Any, AppShellHeaderStyles]
    )
    """Additional styles passed to elements"""
    # no vars
    attributes: AppShellHeaderAttributes
    """Additional attributes passed to elements"""


@ps.react_component("AppShell", "@mantine/core", prop="Header")
def AppShellHeader(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellHeaderProps]
): ...


AppShellNavbarStylesNames = Literal["navbar"]
AppShellNavbarAttributes = dict[AppShellNavbarStylesNames, dict[str, Any]]
AppShellNavbarStyles = dict[AppShellNavbarStylesNames, ps.CSSProperties]
AppShellNavbarClassNames = dict[AppShellNavbarStylesNames, str]


class AppShellNavbarProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLDivProps, BoxProps, AppShellCompoundProps, total=False
):
    # Styles API
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AppShellNavbarClassNames
        | StyleFn[AppShellNavbarProps, Any, AppShellNavbarClassNames]
    )
    """Additional class names passed to elements"""
    styles: (
        AppShellNavbarStyles | StyleFn[AppShellNavbarProps, Any, AppShellNavbarStyles]
    )
    """Additional styles passed to elements"""
    # no vars
    attributes: AppShellNavbarAttributes
    """Additional attributes passed to elements"""


@ps.react_component("AppShell", "@mantine/core", prop="Navbar")
def AppShellNavbar(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellNavbarProps]
): ...


AppShellMainStylesNames = Literal["main"]
AppShellMainStyles = dict[AppShellMainStylesNames, ps.CSSProperties]
AppShellMainClassNames = dict[AppShellMainStylesNames, str]


class AppShellMainProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLMainProps, BoxProps, AppShellCompoundProps, total=False
):
    # Styles API
    # unstyled -> compound component, skip
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AppShellMainClassNames | StyleFn[AppShellMainProps, Any, AppShellMainClassNames]
    )
    """Additional class names passed to elements"""
    styles: AppShellMainStyles | StyleFn[AppShellMainProps, Any, AppShellMainStyles]
    """Additional styles passed to elements"""
    # no vars
    # attributes -> compound component, skip


@ps.react_component("AppShell", "@mantine/core", prop="Main")
def AppShellMain(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellMainProps]
): ...


AppShellFooterStylesNames = Literal["footer"]
AppShellFooterAttributes = dict[AppShellFooterStylesNames, dict[str, Any]]
AppShellFooterStyles = dict[AppShellFooterStylesNames, ps.CSSProperties]
AppShellFooterClassNames = dict[AppShellFooterStylesNames, str]


class AppShellFooterProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLFooterProps, BoxProps, AppShellCompoundProps, total=False
):
    # Styles API
    unstyled: bool
    variant: str
    classNames: (
        AppShellFooterClassNames
        | StyleFn[AppShellFooterProps, Any, AppShellFooterClassNames]
    )
    styles: (
        AppShellFooterStyles | StyleFn[AppShellFooterProps, Any, AppShellFooterStyles]
    )
    # no vars
    attributes: AppShellFooterAttributes


@ps.react_component("AppShell", "@mantine/core", prop="Footer")
def AppShellFooter(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AppShellFooterProps]
): ...


AppShellSectionStylesNames = Literal["section"]
AppShellSectionStyles = dict[AppShellSectionStylesNames, ps.CSSProperties]
AppShellSectionClassNames = dict[AppShellSectionStylesNames, str]


class AppShellSectionProps(  # pyright: ignore[reportIncompatibleVariableOverride]
    ps.HTMLSectionProps, BoxProps, AppShellCompoundProps, total=False
):
    grow: bool
    "If set, the section expands to take all available space"

    # Styles API
    # unstyled -> compound component, skip
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AppShellSectionClassNames
        | StyleFn[AppShellSectionProps, Any, AppShellSectionClassNames]
    )
    """Additional class names passed to elements"""
    styles: (
        AppShellSectionStyles
        | StyleFn[AppShellSectionProps, Any, AppShellSectionStyles]
    )
    """Additional styles passed to elements"""
    # no vars
    # attributes -> compound component, skip


@ps.react_component("AppShell", "@mantine/core", prop="Section")
def AppShellSection(
    *children: ps.Child,
    key: Optional[str] = None,
    **props: Unpack[AppShellSectionProps],
): ...
