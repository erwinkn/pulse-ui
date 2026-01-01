from typing import Unpack

import pulse as ps
from pulse.dom.elements import GenericHTMLElement


class LucideProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	size: str | int
	absoluteStrokeWidth: bool


def lucide_signature(
	*children: ps.Node, key: str | None = None, **props: Unpack[LucideProps]
) -> ps.Element: ...
