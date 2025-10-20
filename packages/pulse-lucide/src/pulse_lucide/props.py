import pulse as ps
from pulse.html.elements import GenericHTMLElement
from pulse.react_component import prop_spec_from_typeddict


class LucideProps(ps.HTMLSVGProps[GenericHTMLElement], total=False):
	size: str | int
	absoluteStrokeWidth: bool


LUCIDE_PROPS_SPEC = prop_spec_from_typeddict(LucideProps)
