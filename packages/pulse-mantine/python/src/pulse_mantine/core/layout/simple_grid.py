from __future__ import annotations

from typing import Any, Literal, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn, StyleProp
from ..theme import MantineSpacing

SimpleGridStylesNames = Literal["root", "container"]
SimpleGridAttributes = dict[SimpleGridStylesNames, dict[str, Any]]
SimpleGridStyles = dict[SimpleGridStylesNames, ps.CSSProperties]
SimpleGridClassNames = dict[SimpleGridStylesNames, str]


class SimpleGridProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	cols: StyleProp[int]
	"""Number of columns @default `1`"""
	spacing: StyleProp[MantineSpacing]
	"""Spacing between columns @default `'md'`"""
	verticalSpacing: StyleProp[MantineSpacing]
	"""Spacing between rows @default `'md'`"""
	type: Literal["media", "container"]
	"""Determines typeof of queries that are used for responsive styles @default `'media'`"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: (
		SimpleGridClassNames | StyleFn[SimpleGridProps, Any, SimpleGridClassNames]
	)
	"""Additional class names passed to elements"""
	styles: SimpleGridStyles | StyleFn[SimpleGridProps, Any, SimpleGridStyles]
	"""Additional styles passed to elements"""
	# no vars
	attributes: SimpleGridAttributes
	"""Additional attributes passed to elements"""


@ps.react_component("SimpleGrid", "@mantine/core")
def SimpleGrid(
	*children: ps.Child, key: str | None = None, **props: Unpack[SimpleGridProps]
): ...
