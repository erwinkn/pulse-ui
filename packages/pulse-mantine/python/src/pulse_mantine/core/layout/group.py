from __future__ import annotations

from typing import Any, Literal, TypedDict, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn
from ..theme import MantineSpacing

GroupStylesNames = Literal["root"]
GroupAttributes = dict[GroupStylesNames, dict[str, Any]]
GroupStyles = dict[GroupStylesNames, ps.CSSProperties]
GroupClassNames = dict[GroupStylesNames, str]


class GroupCtx(TypedDict):
	childWidth: str


class GroupCSSVariables(TypedDict, total=False):
	root: dict[
		Literal[
			"--group-gap",
			"--group-align",
			"--group-justify",
			"--group-wrap",
			"--group-child-width",
		],
		str,
	]


class GroupProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	justify: str
	"""Controls `justify-content` CSS property @default `'flex-start'`"""
	align: str
	"""Controls `align-items` CSS property @default `'center'`"""
	wrap: str
	"""Controls `flex-wrap` CSS property @default `'wrap'`"""
	gap: MantineSpacing
	"""Key of `theme.spacing` or any valid CSS value for `gap`, numbers are converted to rem @default `'md'`"""
	grow: bool
	"""Determines whether each child element should have `flex-grow: 1` style @default `false`"""
	preventGrowOverflow: bool
	"""Determines whether children should take only dedicated amount of space (`max-width` style is set based on the number of children) @default `true`"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: GroupClassNames | StyleFn[GroupProps, GroupCtx, GroupClassNames]
	"""Additional class names passed to elements"""
	styles: GroupStyles | StyleFn[GroupProps, GroupCtx, GroupStyles]
	"""Additional styles passed to elements"""
	vars: GroupCSSVariables
	"""CSS variables for the component"""
	attributes: GroupAttributes
	"""Additional attributes passed to elements"""


@ps.react_component(ps.Import("Group", "@mantine/core"))
def Group(*children: ps.Node, key: str | None = None, **props: Unpack[GroupProps]): ...
