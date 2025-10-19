from __future__ import annotations

from typing import Any, Literal, TypedDict, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn, StyleProp
from ..theme import MantineSpacing
from ..types import MantineBreakpoint

GridStylesNames = Literal["root", "col", "inner", "container"]
GridAttributes = dict[GridStylesNames, dict[str, Any]]
GridStyles = dict[GridStylesNames, ps.CSSProperties]
GridClassNames = dict[GridStylesNames, str]

GridBreakpoints = dict[MantineBreakpoint, str]


class GridCSSVariables(TypedDict, total=False):
	root: dict[Literal["--grid-justify", "--grid-align", "--grid-overflow"], str]


class GridProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	gutter: StyleProp[MantineSpacing]
	"""Gutter between columns, key of `theme.spacing` or any valid CSS value @default `'md'`"""
	grow: bool
	"""If set, columns in the last row expand to fill all available space @default `false`"""
	justify: str
	"""Sets `justify-content` @default `flex-start`"""
	align: str
	"""Sets `align-items` @default `stretch`"""
	columns: int
	"""Number of columns in each row @default `12`"""
	overflow: str
	"""Sets `overflow` CSS property on the root element @default `'visible'`"""
	type: Literal["media", "container"]
	"""Type of queries used for responsive styles @default `'media'`"""
	breakpoints: GridBreakpoints
	"""Breakpoints values, only used with `type="container"`"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: GridClassNames | StyleFn[GridProps, Any, GridClassNames]
	"""Additional class names passed to elements"""
	styles: GridStyles | StyleFn[GridProps, Any, GridStyles]
	"""Additional styles passed to elements"""
	vars: GridCSSVariables
	"""CSS variables for the component"""
	attributes: GridAttributes
	"""Additional attributes passed to elements"""


@ps.react_component("Grid", "@mantine/core")
def Grid(*children: ps.Child, key: str | None = None, **props: Unpack[GridProps]): ...


GridColStylesNames = Literal["root", "col", "inner", "container"]
GridColAttributes = dict[GridColStylesNames, dict[str, Any]]
GridColStyles = dict[GridColStylesNames, ps.CSSProperties]
GridColClassNames = dict[GridColStylesNames, str]


class GridColCSSVariables(TypedDict, total=False):
	root: dict[Literal["--grid-justify", "--grid-align", "--grid-overflow"], str]


ColSpan = float | Literal["auto", "content"]


class GridColProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	span: StyleProp[ColSpan]
	"Column span @default `12`"
	order: StyleProp[int]
	"Column order, can be used to reorder columns at different viewport sizes"
	offset: StyleProp[int]
	"Column offset on the left side – number of columns that are left empty before this column"

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: GridColClassNames | StyleFn[GridColProps, Any, GridColClassNames]
	"""Additional class names passed to elements"""
	styles: GridColStyles | StyleFn[GridColProps, Any, GridColStyles]
	"""Additional styles passed to elements"""
	vars: GridColCSSVariables
	"""CSS variables for the component"""
	attributes: GridColAttributes
	"""Additional attributes passed to elements"""


@ps.react_component("GridCol", "@mantine/core")
def GridCol(
	*children: ps.Child, key: str | None = None, **props: Unpack[GridColProps]
): ...
