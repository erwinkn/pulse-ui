from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

import pulse as ps

from .types import (
	MantineBreakpointsValues,
	MantineColor,
	MantineColorShade,
	MantineFontSizesValues,
	MantineTextWrap,
)


class VariantColorsResolverInput(TypedDict):
	color: MantineColor | None
	theme: MantineTheme
	variant: str
	gradient: NotRequired[MantineGradient]
	autoContrast: NotRequired[bool]


class VariantColorResolverResult(TypedDict):
	background: str
	hover: str
	color: str
	border: str
	hoverColor: NotRequired[str]


VariantColorsResolver = ps.JsFunction[
	[VariantColorsResolverInput], VariantColorResolverResult
]


class MantineTheme(TypedDict):
	focusRing: Literal["auto", "always", "never"]
	"""Controls focus ring styles. Supports the following options:
    *  - `auto` – focus ring is displayed only when the user navigates with keyboard (default value)
    *  - `always` – focus ring is displayed when the user navigates with keyboard and mouse
    *  - `never` – focus ring is always hidden (not recommended)
    """
	scale: float
	"""Rem units scale, change if you customize font-size of `<html />` element
     *  default value is `1` (for `100%`/`16px` font-size on `<html />`)
     """
	fontSmoothing: bool
	"""Determines whether `font-smoothing` property should be set on the body, `true` by default"""
	white: str
	"""White color"""
	black: str
	"""Black color"""
	colors: MantineThemeColors
	"""Object of colors, key is color name, value is an array of at least 10 strings (colors)"""
	primaryShade: MantineColorShade | MantinePrimaryShade
	"""Index of theme.colors[color].
     *  Primary shade is used in all components to determine which color from theme.colors[color] should be used.
     *  Can be either a number (0–9) or an object to specify different color shades for light and dark color schemes.
     *  Default value `{ light: 6, dark: 8 }`
     *
     *  For example,
     *  { primaryShade: 6 } // shade 6 is used both for dark and light color schemes
     *  { primaryShade: { light: 6, dark: 7 } } // different shades for dark and light color schemes
     """
	primaryColor: str
	"""Key of `theme.colors`, hex/rgb/hsl values are not supported.
     *  Determines which color will be used in all components by default.
     *  Default value – `blue`.
     """
	variantColorResolver: VariantColorsResolver
	"""Function to resolve colors based on variant.
     *  Can be used to deeply customize how colors are applied to `Button`, `ActionIcon`, `ThemeIcon`
     *  and other components that use colors from theme.
     """
	autoContrast: bool
	"""Determines whether text color must be changed based on the given `color` prop in filled variant
     *  For example, if you pass `color="blue.1"` to Button component, text color will be changed to `var(--mantine-color-black)`
     *  Default value – `false`
     """
	luminanceThreshold: float
	"""Determines which luminance value is used to determine if text color should be light or dark.
     *  Used only if `theme.autoContrast` is set to `true`.
     *  Default value is `0.3`
     """
	fontFamily: str
	"""Font-family used in all components, system fonts by default"""
	fontFamilyMonospace: str
	"""Monospace font-family, used in code and other similar components, system fonts by default"""
	headings: MantineHeadings
	"""Controls various styles of h1-h6 elements, used in Typography and Title components"""
	radius: MantineRadiusValues
	"""Object of values that are used to set `border-radius` in all components that support it"""
	defaultRadius: MantineRadius
	"""Key of `theme.radius` or any valid CSS value. Default `border-radius` used by most components"""
	spacing: MantineSpacingValues
	"""Object of values that are used to set various CSS properties that control spacing between elements"""
	fontSizes: MantineFontSizesValues
	"""Object of values that are used to control `font-size` property in all components"""
	lineHeights: MantineLineHeightValues
	"""Object of values that are used to control `line-height` property in `Text` component"""
	breakpoints: MantineBreakpointsValues
	"""Object of values that are used to control breakpoints in all components,
     *  values are expected to be defined in em
     """
	shadows: MantineShadowsValues
	"""Object of values that are used to add `box-shadow` styles to components that support `shadow` prop"""
	respectReducedMotion: bool
	"""Determines whether user OS settings to reduce motion should be respected, `false` by default"""
	cursorType: Literal["default", "pointer"]
	"""Determines which cursor type will be used for interactive elements
     * - `default` – cursor that is used by native HTML elements, for example, `input[type="checkbox"]` has `cursor: default` styles
     * - `pointer` – sets `cursor: pointer` on interactive elements that do not have these styles by default
     """
	defaultGradient: MantineGradient
	"""Default gradient configuration for components that support `variant="gradient"`"""
	activeClassName: str
	"""Class added to the elements that have active styles, for example, `Button` and `ActionIcon`"""
	focusClassName: str
	"""Class added to the elements that have focus styles, for example, `Button` or `ActionIcon`.
     *  Overrides `theme.focusRing` property.
     """
	components: MantineThemeComponents
	"""Allows adding `classNames`, `styles` and `defaultProps` to any component"""
	other: MantineThemeOther
	"""Any other properties that you want to access with the theme objects"""


class MantineThemeOverride(TypedDict, total=False):
	"""Partial version of MantineTheme."""

	focusRing: Literal["auto", "always", "never"]
	"""Controls focus ring styles. Supports the following options:
    *  - `auto` – focus ring is displayed only when the user navigates with keyboard (default value)
    *  - `always` – focus ring is displayed when the user navigates with keyboard and mouse
    *  - `never` – focus ring is always hidden (not recommended)
    """
	scale: float
	"""Rem units scale, change if you customize font-size of `<html />` element
     *  default value is `1` (for `100%`/`16px` font-size on `<html />`)
     """
	fontSmoothing: bool
	"""Determines whether `font-smoothing` property should be set on the body, `true` by default"""
	white: str
	"""White color"""
	black: str
	"""Black color"""
	colors: MantineThemeColors
	"""Object of colors, key is color name, value is an array of at least 10 strings (colors)"""
	primaryShade: MantineColorShade | MantinePrimaryShade
	"""Index of theme.colors[color].
     *  Primary shade is used in all components to determine which color from theme.colors[color] should be used.
     *  Can be either a number (0–9) or an object to specify different color shades for light and dark color schemes.
     *  Default value `{ light: 6, dark: 8 }`
     *
     *  For example,
     *  { primaryShade: 6 } // shade 6 is used both for dark and light color schemes
     *  { primaryShade: { light: 6, dark: 7 } } // different shades for dark and light color schemes
     """
	primaryColor: str
	"""Key of `theme.colors`, hex/rgb/hsl values are not supported.
     *  Determines which color will be used in all components by default.
     *  Default value – `blue`.
     """
	variantColorResolver: VariantColorsResolver
	"""Function to resolve colors based on variant.
     *  Can be used to deeply customize how colors are applied to `Button`, `ActionIcon`, `ThemeIcon`
     *  and other components that use colors from theme.
     """
	autoContrast: bool
	"""Determines whether text color must be changed based on the given `color` prop in filled variant
     *  For example, if you pass `color="blue.1"` to Button component, text color will be changed to `var(--mantine-color-black)`
     *  Default value – `false`
     """
	luminanceThreshold: float
	"""Determines which luminance value is used to determine if text color should be light or dark.
     *  Used only if `theme.autoContrast` is set to `true`.
     *  Default value is `0.3`
     """
	fontFamily: str
	"""Font-family used in all components, system fonts by default"""
	fontFamilyMonospace: str
	"""Monospace font-family, used in code and other similar components, system fonts by default"""
	headings: MantineHeadings
	"""Controls various styles of h1-h6 elements, used in Typography and Title components"""
	radius: MantineRadiusValues
	"""Object of values that are used to set `border-radius` in all components that support it"""
	defaultRadius: MantineRadius
	"""Key of `theme.radius` or any valid CSS value. Default `border-radius` used by most components"""
	spacing: MantineSpacingValues
	"""Object of values that are used to set various CSS properties that control spacing between elements"""
	fontSizes: MantineFontSizesValues
	"""Object of values that are used to control `font-size` property in all components"""
	lineHeights: MantineLineHeightValues
	"""Object of values that are used to control `line-height` property in `Text` component"""
	breakpoints: MantineBreakpointsValues
	"""Object of values that are used to control breakpoints in all components,
     *  values are expected to be defined in em
     """
	shadows: MantineShadowsValues
	"""Object of values that are used to add `box-shadow` styles to components that support `shadow` prop"""
	respectReducedMotion: bool
	"""Determines whether user OS settings to reduce motion should be respected, `false` by default"""
	cursorType: Literal["default", "pointer"]
	"""Determines which cursor type will be used for interactive elements
     * - `default` – cursor that is used by native HTML elements, for example, `input[type="checkbox"]` has `cursor: default` styles
     * - `pointer` – sets `cursor: pointer` on interactive elements that do not have these styles by default
     """
	defaultGradient: MantineGradient
	"""Default gradient configuration for components that support `variant="gradient"`"""
	activeClassName: str
	"""Class added to the elements that have active styles, for example, `Button` and `ActionIcon`"""
	focusClassName: str
	"""Class added to the elements that have focus styles, for example, `Button` or `ActionIcon`.
     *  Overrides `theme.focusRing` property.
     """
	components: MantineThemeComponents
	"""Allows adding `classNames`, `styles` and `defaultProps` to any component"""
	other: MantineThemeOther
	"""Any other properties that you want to access with the theme objects"""


MantineStylesRecord = dict[str, ps.CSSProperties]


class MantineThemeComponent(TypedDict, total=False):
	classNames: Any
	styles: Any
	vars: Any
	defaultProps: Any


MantineThemeComponents = dict[str, MantineThemeComponent]


class HeadingStyle(TypedDict):
	fontSize: str
	fontWeight: NotRequired[str]
	lineHeight: str


class MantineThemeSizesOverride(TypedDict):
	pass


class MantineHeadings(TypedDict):
	fontFamily: str
	fontWeight: str
	textWrap: MantineTextWrap
	sizes: dict[str, HeadingStyle]


MantineRadius = str | float  # Simplified from complex conditional type
MantineRadiusValues = dict[str, str]  # Simplified from complex conditional type
MantineSpacing = str | float  # Simplified from complex conditional type
MantineSpacingValues = dict[str, str]  # Simplified from complex conditional type
MantineShadow = str  # Simplified from complex conditional type
MantineShadowsValues = dict[str, str]  # Simplified from complex conditional type
MantineLineHeight = str  # Simplified from complex conditional type
MantineLineHeightValues = dict[str, str]  # Simplified from complex conditional type


class MantineThemeOther(TypedDict):
	"""Any other properties that you want to access with the theme objects"""

	pass


class MantineGradient(TypedDict):
	from_: str
	to: str
	deg: NotRequired[float]


MantineColorsTuple = tuple[str, ...]


class MantinePrimaryShade(TypedDict):
	light: MantineColorShade
	dark: MantineColorShade


MantineThemeColors = dict[
	str, MantineColorsTuple
]  # Simplified from complex conditional type
