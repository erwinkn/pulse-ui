from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, Unpack
import pulse as ps
from ..styles import StyleFn
from ..box import BoxProps

AspectRatioStylesNames = Literal["root"]
AspectRatioAttributes = dict[AspectRatioStylesNames, dict[str, Any]]
AspectRatioStyles = dict[AspectRatioStylesNames, ps.CSSProperties]
AspectRatioClassNames = dict[AspectRatioStylesNames, str]


class AspectRatioCSSVariables(TypedDict, total=False):
    root: dict[Literal["--ar-ratio"], str]


class AspectRatioProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
    ratio: float
    "Aspect ratio, for example, `16 / 9`, `4 / 3`, `1920 / 1080` @default `1`"

    # Styles API props
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""
    classNames: (
        AspectRatioClassNames | StyleFn[AspectRatioProps, Any, AspectRatioClassNames]
    )
    """Additional class names passed to elements"""
    styles: AspectRatioStyles | StyleFn[AspectRatioProps, Any, AspectRatioStyles]
    """Additional styles passed to elements"""
    vars: StyleFn[AspectRatioProps, Any, AspectRatioCSSVariables]
    """CSS variables for the component"""
    attributes: AspectRatioAttributes
    """Additional attributes passed to elements"""


@ps.react_component("AspectRatio", "@mantine/core")
def AspectRatio(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[AspectRatioProps]
): ...
