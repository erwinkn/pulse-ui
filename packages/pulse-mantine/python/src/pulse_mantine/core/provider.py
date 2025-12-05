from __future__ import annotations

from typing import Any, Literal, TypedDict, Unpack

import pulse as ps
from pulse.transpiler.imports import CssImport

from .styles import CSSVariables
from .theme import MantineTheme, MantineThemeOverride
from .types import MantineColorScheme

MantineProviderForceColorScheme = Literal["light", "dark"]
MantineProviderEnvironment = Literal["default", "test"]


class MantineProviderProps(TypedDict, total=False):
	"""Theme override object"""

	theme: MantineThemeOverride
	colorSchemeManager: MantineColorSchemeManager
	"""Used to retrieve/set color scheme value in external storage, by default uses `window.localStorage`"""
	defaultColorScheme: MantineColorScheme
	"""Default color scheme value used when `colorSchemeManager` cannot retrieve value from external storage, `light` by default"""
	forceColorScheme: MantineProviderForceColorScheme
	"""Forces color scheme value, if set, MantineProvider ignores `colorSchemeManager` and `defaultColorScheme`"""
	cssVariablesSelector: str
	"""CSS selector to which CSS variables should be added, `:root` by default"""
	withCssVariables: bool
	"""Determines whether theme CSS variables should be added to given `cssVariablesSelector` @default `true`"""
	deduplicateCssVariables: bool
	"""Determines whether CSS variables should be deduplicated: if CSS variable has the same value as in default theme, it is not added in the runtime. @default `true`."""
	getRootElement: ps.JsFunction[ps.HTMLElement | None]
	"""Function to resolve root element to set `data-mantine-color-scheme` attribute, must return undefined on server, `() => document.documentElement` by default"""
	classNamesPrefix: str
	"""A prefix for components static classes (for example {selector}-Text-root), `mantine` by default"""
	getStyleNonce: ps.JsFunction[str]
	"""Function to generate nonce attribute added to all generated `<style />` tags"""
	cssVariablesResolver: CSSVariablesResolver
	"""Function to generate CSS variables based on theme object"""
	withStaticClasses: bool
	"""Determines whether components should have static classes, for example, `mantine-Button-root`. @default `true`"""
	withGlobalClasses: bool
	"""Determines whether global classes should be added with `<style />` tag. Global classes are required for `hiddenFrom`/`visibleFrom` and `lightHidden`/`darkHidden` props to work. @default `true`."""
	stylesTransform: MantineStylesTransform
	"""An object to transform `styles` and `sx` props into css classes, can be used with CSS-in-JS libraries"""
	env: MantineProviderEnvironment
	"""Environment at which the provider is used, `'test'` environment disables all transitions and portals"""


@ps.react_component(
	"MantineProvider",
	"@mantine/core",
	extra_imports=[
		CssImport(
			"@mantine/core/styles.css",
			# Ensure core styles load before dates/charts styles if present
			before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
		)
	],
)
def MantineProvider(*children: ps.Child, key: str | None = None, **props: Any): ...


class MantineStylesTransform(TypedDict, total=False):
	sx: ps.JsFunction[ps.JsFunction[Any, str]]
	styles: ps.JsFunction[ps.JsFunction[Any, Any, dict[str, str]]]


class ConvertCSSVariablesInput(TypedDict):
	variables: CSSVariables
	"Shared CSS variables that should be accessible independent from color scheme"
	dark: CSSVariables
	"CSS variables available only in dark color scheme"
	light: CSSVariables
	"CSS variables available only in light color scheme"


CSSVariablesResolver = ps.JsFunction[MantineTheme, ConvertCSSVariablesInput]


class MantineColorSchemeManager(TypedDict):
	get: ps.JsFunction[MantineColorScheme, MantineColorScheme]
	"""Function to retrieve color scheme value from external storage, for example window.localStorage
    
    JS: get: (defaultValue: MantineColorScheme) => MantineColorScheme"""

	set: ps.JsFunction[MantineColorScheme, None]
	"""Function to set color scheme value in external storage, for example window.localStorage
    
    JS: set: (value: MantineColorScheme) => void"""

	subscribe: ps.JsFunction[ps.JsFunction[MantineColorScheme, None], None]
	"""Function to subscribe to color scheme changes triggered by external events
    
    JS: subscribe: (onUpdate: (colorScheme: MantineColorScheme) => void) => void"""

	unsubscribe: ps.JsFunction[None]
	"""Function to unsubscribe from color scheme changes triggered by external events
    
    JS: unsubscribe: () => void"""

	clear: ps.JsFunction[None]
	"""Function to clear value from external storage
    
    JS: clear: () => void"""


class HeadlessMantineProviderProps(TypedDict, total=False):
	theme: MantineThemeOverride
	"""Theme override object"""

	env: MantineProviderEnvironment
	"""Environment at which the provider is used, 'test' environment disables all transitions and portals"""


@ps.react_component("HeadlessMantineProvider", "@mantine/core")
def HeadlessMantineProvider(
	*children: ps.Child,
	key: str | None = None,
	**props: Unpack[HeadlessMantineProviderProps],
): ...
