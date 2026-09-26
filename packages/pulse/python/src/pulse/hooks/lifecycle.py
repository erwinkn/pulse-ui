from __future__ import annotations

from contextlib import ExitStack
from types import TracebackType
from typing import Literal, override

from pulse.reactive import Scope
from pulse.resources import Resource, ResourceScope


class InitializationScope(Resource):
	"""Captures resources without attaching effects to the render scope."""

	_resources: ResourceScope

	def __init__(self, label: str | None = None) -> None:
		self._resources = ResourceScope(label=label)
		self._contexts: ExitStack | None = None

	def __enter__(self) -> InitializationScope:
		if self._contexts is not None:
			raise RuntimeError("InitializationScope cannot be entered more than once")
		contexts = ExitStack()
		contexts.enter_context(self._resources)
		contexts.enter_context(Scope())
		self._contexts = contexts
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_tb: TracebackType | None,
	) -> Literal[False]:
		assert self._contexts is not None
		contexts = self._contexts
		self._contexts = None
		contexts.__exit__(exc_type, exc_value, exc_tb)
		return False

	@override
	def dispose(self) -> None:
		if not self._resources.__disposed__:
			self._resources.dispose()


__all__ = ["InitializationScope"]
