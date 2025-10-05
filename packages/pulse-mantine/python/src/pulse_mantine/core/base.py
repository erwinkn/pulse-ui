from __future__ import annotations

from typing import Any, Callable, Sequence, TypeVar, TypedDict
import pulse as ps
from .theme import MantineTheme


class MantineComponentProps(TypedDict, total=False):
    component: str | ps.Element
    "Changes the default element used by the component"
    renderRoot: Callable[[dict[str, Any]], ps.Element]
    """Changes the default element used by the component, depending on props."""

