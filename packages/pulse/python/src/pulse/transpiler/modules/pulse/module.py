"""Main pulse module transpilation."""

from typing import final

from pulse.components.react_router import Link as Link
from pulse.components.react_router import Outlet as Outlet
from pulse.transpiler.modules.pulse.tags import PulseTags


@final
class PulseModule(PulseTags):
	"""Provides transpilation for the public pulse module."""

	Link = Link
	Outlet = Outlet
