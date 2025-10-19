import pulse as ps
from pulse.react_component import _propspec_from_typeddict


class LucideProps(ps.HTMLSVGProps, total=False):
	size: str | int
	absoluteStrokeWidth: bool


LUCIDE_PROPS_SPEC = _propspec_from_typeddict(LucideProps)
