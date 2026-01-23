import asyncio
from collections.abc import Awaitable, Callable
from typing import (
	Any,
	Literal,
	Protocol,
	override,
)

from pulse.helpers import MISSING
from pulse.reactive import AsyncEffect, Computed, Signal


class Fetcher(Protocol):
	is_fetching: Signal[bool]
	data: Signal[Any]
	status: Signal[Literal["loading", "success", "error"]]


class AsyncQueryEffect(AsyncEffect):
	"""
	Specialized AsyncEffect for queries that synchronously sets loading state
	when rescheduled/run.

	For unkeyed queries (deps=None), also resets data/status when re-running
	due to dependency changes, to behave like keyed queries on key change.
	"""

	fetcher: Fetcher
	_is_unkeyed: bool

	def __init__(
		self,
		fn: Callable[[], Awaitable[None]],
		fetcher: Fetcher,
		name: str | None = None,
		lazy: bool = False,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
	):
		self.fetcher = fetcher
		# Unkeyed queries have deps=None (auto-track), keyed have deps=[] (no auto-track)
		self._is_unkeyed = deps is None
		super().__init__(fn, name=name, lazy=lazy, deps=deps)

	@override
	def run(self) -> asyncio.Task[Any]:
		# Immediately set loading state before running the effect
		self.fetcher.is_fetching.write(True)

		# For unkeyed queries on re-run (dependency changed), reset data/status
		# to behave like keyed queries when key changes (new Query with data=None)
		if self._is_unkeyed and self.runs > 0:
			self.fetcher.data.write(MISSING)
			self.fetcher.status.write("loading")

		return super().run()
