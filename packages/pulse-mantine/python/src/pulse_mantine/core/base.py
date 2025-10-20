from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

import pulse as ps


class MantineComponentProps(TypedDict, total=False):
	component: str | ps.Element
	"Changes the default element used by the component"
	renderRoot: Callable[[dict[str, Any]], ps.Element]
	"""Changes the default element used by the component, depending on props."""
