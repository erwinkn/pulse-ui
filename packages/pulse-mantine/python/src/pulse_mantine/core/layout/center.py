from __future__ import annotations

from typing import Any, Literal, Unpack

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn

CenterStylesNames = Literal["root"]
CenterAttributes = dict[CenterStylesNames, dict[str, Any]]
CenterStyles = dict[CenterStylesNames, ps.CSSProperties]
CenterClassNames = dict[CenterStylesNames, str]


class CenterProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
	inline: bool
	"If set, `inline-flex` is used instead of `flex`"

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	variant: str
	"""Component variant, if applicable"""
	classNames: CenterClassNames | StyleFn[CenterProps, Any, CenterClassNames]
	"""Additional class names passed to elements"""
	styles: CenterStyles | StyleFn[CenterProps, Any, CenterStyles]
	"""Additional styles passed to elements"""
	# no vars
	attributes: CenterAttributes
	"""Additional attributes passed to elements"""


@ps.react_component(ps.Import("Center", "@mantine/core"))
def Center(
	*children: ps.Node, key: str | None = None, **props: Unpack[CenterProps]
): ...
