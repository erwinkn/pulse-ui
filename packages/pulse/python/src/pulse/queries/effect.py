import asyncio
from collections.abc import Awaitable, Callable
from typing import (
	Any,
	Protocol,
	override,
)

from pulse.queries.common import QueryFetchStatus
from pulse.reactive import AsyncEffect, Computed, Signal


class Fetcher(Protocol):
	fetch_status: Signal[QueryFetchStatus]


class AsyncQueryEffect(AsyncEffect):
	"""
	Specialized AsyncEffect for queries that synchronously sets loading state
	when rescheduled/run.
	"""

	fetcher: Fetcher

	def __init__(
		self,
		fn: Callable[[], Awaitable[None]],
		fetcher: Fetcher,
		name: str | None = None,
		lazy: bool = False,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
	):
		self.fetcher = fetcher
		super().__init__(fn, name=name, lazy=lazy, deps=deps)

	@override
	def run(self) -> asyncio.Task[Any]:
		# Immediately set loading state before running the effect
		self.fetcher.fetch_status.write("fetching")
		return super().run()
