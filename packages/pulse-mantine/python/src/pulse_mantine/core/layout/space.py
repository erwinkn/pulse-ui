from __future__ import annotations

from typing import Optional, Unpack
import pulse as ps
from ..box import BoxProps


class SpaceProps(ps.HTMLDivProps, BoxProps, total=False):  # pyright: ignore[reportIncompatibleVariableOverride]
    # Styles API props
    unstyled: bool
    """Removes default styles from the component"""
    variant: str
    """Component variant, if applicable"""

    # no classNames, styles, vars, attributes


@ps.react_component("Space", "@mantine/core")
def Space(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[SpaceProps]
): ...
