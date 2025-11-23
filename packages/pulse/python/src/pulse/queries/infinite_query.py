import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, cast, override

from pulse.helpers import MISSING, call_flexible, maybe_await
from pulse.queries.query import (
	RETRY_DELAY_DEFAULT,
	Query,
	QueryFetchStatus,
	QueryKey,
)
from pulse.reactive import Signal

TPage = TypeVar("TPage")
TPageParam = TypeVar("TPageParam")
PageDirection = Literal["forward", "backward"]


@dataclass(slots=True)
class InfiniteQueryConfig(Generic[TPage, TPageParam]):
	"""Configuration for InfiniteQuery. Contains all QueryConfig fields plus infinite query specific options."""

	retries: int
	retry_delay: float
	initial_data: list[TPage] | Callable[[], list[TPage]] | None
	gc_time: float
	on_dispose: Callable[[Any], None] | None
	initial_page_param: TPageParam
	get_next_page_param: Callable[
		[TPage, list[TPage], TPageParam, list[TPageParam]], TPageParam | None
	]
	get_previous_page_param: (
		Callable[[TPage, list[TPage], TPageParam, list[TPageParam]], TPageParam | None]
		| None
	)
	max_pages: int


@dataclass(slots=True)
class InfiniteQueryFunctionContext(Generic[TPageParam]):
	"""Context passed to the query function for each page fetch."""

	page_param: TPageParam
	direction: PageDirection


class InfiniteQuery(Generic[TPage, TPageParam], Query[list[TPage]]):
	"""
	Query variant that manages paginated data with forward/backward fetching.
	"""

	query_fn: Callable[[InfiniteQueryFunctionContext[TPageParam]], Awaitable[TPage]]
	cfg: InfiniteQueryConfig[TPage, TPageParam]

	pages: Signal[list[TPage] | None]
	page_params: Signal[list[TPageParam]]
	has_next_page: Signal[bool]
	has_previous_page: Signal[bool]
	is_fetching_next_page: Signal[bool]
	is_fetching_previous_page: Signal[bool]

	_next_task: asyncio.Task[Any] | None
	_prev_task: asyncio.Task[Any] | None

	def __init__(
		self,
		key: QueryKey | None,
		query_fn: Callable[
			[InfiniteQueryFunctionContext[TPageParam]], Awaitable[TPage]
		],
		*,
		initial_page_param: TPageParam,
		get_next_page_param: Callable[
			[TPage, list[TPage], TPageParam, list[TPageParam]], TPageParam | None
		],
		get_previous_page_param: Callable[
			[TPage, list[TPage], TPageParam, list[TPageParam]], TPageParam | None
		]
		| None = None,
		max_pages: int = 0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: list[TPage] | None = MISSING,  # pyright: ignore[reportArgumentType]
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.query_fn = query_fn

		self.cfg = InfiniteQueryConfig[TPage, TPageParam](  # pyright: ignore[reportIncompatibleVariableOverride]
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			gc_time=gc_time,
			on_dispose=on_dispose,
			initial_page_param=initial_page_param,
			get_next_page_param=get_next_page_param,
			get_previous_page_param=get_previous_page_param,
			max_pages=max_pages,
		)

		self.pages = Signal(
			none_if_missing(initial_data), name=f"inf_query.pages({key})"
		)
		self.page_params = Signal([], name=f"inf_query.page_params({key})")
		self.has_next_page = Signal(False, name=f"inf_query.has_next({key})")
		self.has_previous_page = Signal(False, name=f"inf_query.has_prev({key})")
		self.is_fetching_next_page = Signal(
			False, name=f"inf_query.is_fetching_next({key})"
		)
		self.is_fetching_previous_page = Signal(
			False, name=f"inf_query.is_fetching_prev({key})"
		)

		self._next_task = None
		self._prev_task = None

		# Pass a placeholder fn; _run is overridden and uses query_fn instead.
		async def _placeholder() -> list[TPage]:
			return []

		super().__init__(
			key,
			_placeholder,
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			gc_time=gc_time,
			on_dispose=on_dispose,
		)

	def _context(self, page_param: TPageParam, direction: PageDirection):
		return InfiniteQueryFunctionContext(page_param=page_param, direction=direction)

	def _compute_next_param(self) -> TPageParam | None:
		pages = self.pages.read() or []
		params = self.page_params.read()
		if len(pages) == 0:
			return self.cfg.initial_page_param
		last_page = pages[-1]
		last_param = params[-1]
		return self.cfg.get_next_page_param(last_page, pages, last_param, params)

	def _compute_previous_param(self) -> TPageParam | None:
		if self.cfg.get_previous_page_param is None:
			return None
		pages = self.pages.read() or []
		params = self.page_params.read()
		if len(pages) == 0:
			return None
		first_page = pages[0]
		first_param = params[0]
		return self.cfg.get_previous_page_param(first_page, pages, first_param, params)

	def _update_has_more(self, pages: list[TPage], params: list[TPageParam]):
		if len(pages) == 0:
			self.has_next_page.write(False)
			self.has_previous_page.write(self.cfg.get_previous_page_param is not None)
			return
		next_param = self.cfg.get_next_page_param(pages[-1], pages, params[-1], params)
		prev_param = (
			self.cfg.get_previous_page_param(pages[0], pages, params[0], params)
			if self.cfg.get_previous_page_param
			else None
		)
		self.has_next_page.write(next_param is not None)
		self.has_previous_page.write(prev_param is not None)

	def _trim_if_needed(
		self,
		pages: list[TPage],
		params: list[TPageParam],
		direction: PageDirection,
	):
		if (
			self.cfg.max_pages
			and self.cfg.max_pages > 0
			and len(pages) > self.cfg.max_pages
		):
			over = len(pages) - self.cfg.max_pages
			for _ in range(over):
				if direction == "forward":
					pages.pop(0)
					params.pop(0)
				else:
					pages.pop()
					params.pop()

	def _set_success_pages(
		self,
		pages: list[TPage],
		params: list[TPageParam],
		*,
		manual: bool = False,
	):
		self.pages.write(pages)
		self.page_params.write(params)
		self._update_has_more(pages, params)
		super()._set_success(pages, manual=manual)

	@override
	async def _run(self):
		self.retries.write(0)
		self.retry_reason.write(None)

		while True:
			try:
				page = await self.query_fn(
					self._context(self.cfg.initial_page_param, "forward")
				)
				pages = [page]
				params = [self.cfg.initial_page_param]
				self._set_success_pages(pages, params)
				for obs in self._observers:
					if obs._on_success:  # pyright: ignore[reportPrivateUsage]
						await maybe_await(call_flexible(obs._on_success, pages))  # pyright: ignore[reportPrivateUsage]
				return
			except asyncio.CancelledError:
				raise
			except Exception as e:
				current_retries = self.retries.read()
				if current_retries < self.cfg.retries:
					self._failed_retry(e)
					await asyncio.sleep(self.cfg.retry_delay)
				else:
					self.retry_reason.write(e)
					self._set_error(e)
					for obs in self._observers:
						if obs._on_error:  # pyright: ignore[reportPrivateUsage]
							await maybe_await(call_flexible(obs._on_error, e))  # pyright: ignore[reportPrivateUsage]
					return

	async def fetch_next_page(self, page_param: TPageParam | None = None):
		if self.is_fetching_next_page.read():
			if self._next_task:
				return await self._next_task
			return None

		next_param = (
			page_param if page_param is not None else self._compute_next_param()
		)
		if next_param is None:
			self.has_next_page.write(False)
			return None

		async def runner():
			self.is_fetching_next_page.write(True)
			self.fetch_status.write(cast(QueryFetchStatus, "fetching"))
			try:
				await self._fetch_page(next_param, direction="forward")
			finally:
				self.is_fetching_next_page.write(False)
				self.fetch_status.write(cast(QueryFetchStatus, "idle"))

		self._next_task = asyncio.create_task(runner())
		return await self._next_task

	async def fetch_previous_page(self, page_param: TPageParam | None = None):
		if self.is_fetching_previous_page.read():
			if self._prev_task:
				return await self._prev_task
			return None

		prev_param = (
			page_param if page_param is not None else self._compute_previous_param()
		)
		if prev_param is None:
			self.has_previous_page.write(False)
			return None

		async def runner():
			self.is_fetching_previous_page.write(True)
			self.fetch_status.write(cast(QueryFetchStatus, "fetching"))
			try:
				await self._fetch_page(prev_param, direction="backward")
			finally:
				self.is_fetching_previous_page.write(False)
				self.fetch_status.write(cast(QueryFetchStatus, "idle"))

		self._prev_task = asyncio.create_task(runner())
		return await self._prev_task

	async def _fetch_page(self, page_param: TPageParam, *, direction: PageDirection):
		retries = 0
		while True:
			try:
				page = await self.query_fn(self._context(page_param, direction))
				current_pages = list(self.pages.read() or [])
				current_params = list(self.page_params.read())
				if direction == "forward":
					current_pages.append(page)
					current_params.append(page_param)
				else:
					current_pages.insert(0, page)
					current_params.insert(0, page_param)

				self._trim_if_needed(current_pages, current_params, direction)
				self._set_success_pages(current_pages, current_params)
				for obs in self._observers:
					if obs._on_success:  # pyright: ignore[reportPrivateUsage]
						await maybe_await(call_flexible(obs._on_success, current_pages))  # pyright: ignore[reportPrivateUsage]
				return
			except asyncio.CancelledError:
				raise
			except Exception as e:
				if retries < self.cfg.retries:
					retries += 1
					self._failed_retry(e)
					await asyncio.sleep(self.cfg.retry_delay)
					continue
				self.retry_reason.write(e)
				self._set_error(e)
				for obs in self._observers:
					if obs._on_error:  # pyright: ignore[reportPrivateUsage]
						await maybe_await(call_flexible(obs._on_error, e))  # pyright: ignore[reportPrivateUsage]
				raise

	@override
	async def refetch(self, cancel_refetch: bool = True) -> list[TPage]:
		if cancel_refetch:
			self.effect.cancel()
		await self.wait()
		return self.pages.read() or []

	@override
	def dispose(self):
		if self._next_task and not self._next_task.done():
			self._next_task.cancel()
		if self._prev_task and not self._prev_task.done():
			self._prev_task.cancel()
		super().dispose()


def none_if_missing(value: Any):
	return None if value is MISSING else value
