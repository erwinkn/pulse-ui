import pulse as ps
from pulse.html.types import GenericHTMLElement
from pulse.react_component import _propspec_from_typeddict


class LucideProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	size: str | int
	absoluteStrokeWidth: bool


LUCIDE_PROPS_SPEC = _propspec_from_typeddict(LucideProps)
