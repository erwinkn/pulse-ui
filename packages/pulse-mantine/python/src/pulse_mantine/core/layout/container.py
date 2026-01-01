from __future__ import annotations

from typing import Any, Literal, TypedDict, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn
from ..types import MantineSize

ContainerStylesNames = Literal["root"]
ContainerAttributes = dict[ContainerStylesNames, dict[str, Any]]
ContainerStyles = dict[ContainerStylesNames, ps.CSSProperties]
ContainerClassNames = dict[ContainerStylesNames, str]


class ContainerCSSVariables(TypedDict, total=False):
	root: dict[Literal["--container-size"], str]


class ContainerProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	size: MantineSize | str | float
	"""`max-width` of the container, value is not responsive – it is the same
    for all screen sizes. Numbers are converted to rem. Ignored when `fluid`
    prop is set. @default `'md'`"""
	fluid: bool
	"""If set, the container takes 100% width of its parent and `size` prop is
    ignored. @default `false`"""
	strategy: Literal["block", "grid"]
	"""Centering strategy @default `'block'`"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: ContainerClassNames | StyleFn[ContainerProps, Any, ContainerClassNames]
	"""Additional class names passed to elements"""
	styles: ContainerStyles | StyleFn[ContainerProps, Any, ContainerStyles]
	"""Additional styles passed to elements"""
	vars: ContainerCSSVariables
	"""CSS variables passed to elements"""
	attributes: ContainerAttributes
	"""Additional attributes passed to elements"""


@ps.react_component(ps.Import("Container", "@mantine/core"))
def Container(
	*children: ps.Node, key: str | None = None, **props: Unpack[ContainerProps]
): ...
