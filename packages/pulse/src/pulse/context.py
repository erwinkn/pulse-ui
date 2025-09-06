# This is more for documentation than actually importing from here
from .reactive import REACTIVE_CONTEXT
from .routing import RouteContext  # kept for typing references only

# NOTE: SessionContext objecst set both the SESSION_CONTEXT and REACTIVE_CONTEXT
from .session import PULSE_CONTEXT
from .hooks import HOOK_CONTEXT
from .react_component import COMPONENT_REGISTRY

__all__ = [
    "REACTIVE_CONTEXT",
    # ROUTE_CONTEXT removed; route context available via PULSE_CONTEXT
    "PULSE_CONTEXT",
    "HOOK_CONTEXT",
    "COMPONENT_REGISTRY",
]
