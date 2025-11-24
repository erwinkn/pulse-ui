import asyncio
import datetime as dt
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
	Any,
	Generic,
	Literal,
	NamedTuple,
	TypeVar,
	cast,
	override,
)

from pulse.context import PulseContext
from pulse.helpers import (
	MISSING,
	Disposable,
	call_flexible,
	later,
	maybe_await,
)
from pulse.queries.common import (
	OnErrorFn,
	OnSuccessFn,
	QueryFetchStatus,
	QueryKey,
	QueryStatus,
	bind_state,
)
from pulse.queries.effect import AsyncQueryEffect
from pulse.queries.query import RETRY_DELAY_DEFAULT, QueryConfig
from pulse.reactive import Computed, Effect, Signal, Untrack
from pulse.state import InitializableProperty, State

TPage = TypeVar("TPage")
TPageParam = TypeVar("TPageParam")
TState = TypeVar("TState", bound=State)
PageDirection = Literal["forward", "backward"]


class Page(NamedTuple, Generic[TPage, TPageParam]):
	data: TPage
	param: TPageParam


@dataclass(slots=True)
class InfiniteQueryConfig(
	QueryConfig[list[Page[TPage, TPageParam]]], Generic[TPage, TPageParam]
):
	"""Configuration for InfiniteQuery. Contains all QueryConfig fields plus infinite query specific options."""

	initial_page_param: TPageParam
	get_next_page_param: Callable[[list[Page[TPage, TPageParam]]], TPageParam | None]
	get_previous_page_param: (
		Callable[[list[Page[TPage, TPageParam]]], TPageParam | None] | None
	)
	max_pages: int


class InfiniteQuery(Generic[TPage, TPageParam], Disposable):
	"""Paginated query that stores data as a list of Page(data, param)."""

	key: QueryKey | None
	fn: Callable[[TPageParam], Awaitable[TPage]]
	cfg: InfiniteQueryConfig[TPage, TPageParam]

	# Reactive signals for query state
	data: Signal[list[Page[TPage, TPageParam]] | None]
	error: Signal[Exception | None]
	last_updated: Signal[float]
	status: Signal[QueryStatus]
	fetch_status: Signal[QueryFetchStatus]
	retries: Signal[int]
	retry_reason: Signal[Exception | None]

	has_next_page: Signal[bool]
	has_previous_page: Signal[bool]
	is_fetching_next_page: Signal[bool]
	is_fetching_previous_page: Signal[bool]

	_next_task: asyncio.Task[Any] | None
	_prev_task: asyncio.Task[Any] | None
	_refetch_page: Callable[[TPage, int, list[TPage]], bool] | None

	_observers: list[Any]
	_effect: AsyncQueryEffect | None
	_gc_handle: asyncio.TimerHandle | None

	def __init__(
		self,
		key: QueryKey | None,
		fn: Callable[[TPageParam], Awaitable[TPage]],
		*,
		initial_page_param: TPageParam,
		get_next_page_param: Callable[
			[list[Page[TPage, TPageParam]]], TPageParam | None
		],
		get_previous_page_param: (
			Callable[[list[Page[TPage, TPageParam]]], TPageParam | None] | None
		) = None,
		max_pages: int = 0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: list[Page[TPage, TPageParam]] | None | Any = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.key = key
		self.fn = fn

		self.cfg = InfiniteQueryConfig(
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			on_dispose=on_dispose,
			initial_page_param=initial_page_param,
			get_next_page_param=get_next_page_param,
			get_previous_page_param=get_previous_page_param,
			max_pages=max_pages,
		)

		initial_pages: list[Page[TPage, TPageParam]] | None
		if initial_data is MISSING:
			initial_pages = None
		else:
			initial_pages = cast(list[Page[TPage, TPageParam]] | None, initial_data)

		self.data = Signal(initial_pages, name=f"inf_query.data({key})")
		self.error = Signal(None, name=f"inf_query.error({key})")
		self.last_updated = Signal(0.0, name=f"inf_query.last_updated({key})")
		if initial_data_updated_at:
			self.set_updated_at(initial_data_updated_at)

		self.status = Signal(
			"loading" if initial_pages is None else "success",
			name=f"inf_query.status({key})",
		)
		self.fetch_status = Signal("idle", name=f"inf_query.fetch_status({key})")
		self.retries = Signal(0, name=f"inf_query.retries({key})")
		self.retry_reason = Signal(None, name=f"inf_query.retry_reason({key})")

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
		self._refetch_page = None
		self._observers = []
		self._effect = None
		self._gc_handle = None

	def set_updated_at(self, updated_at: float | dt.datetime):
		if isinstance(updated_at, dt.datetime):
			updated_at = updated_at.timestamp()
		self.last_updated.write(updated_at)

	def set_initial_data(
		self,
		pages: list[Page[TPage, TPageParam]]
		| Callable[[], list[Page[TPage, TPageParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		"""
		Set initial pages while the query is still loading.
		"""
		if self.status() != "loading":
			return
		value = pages() if callable(pages) else pages
		self.set_data(value, updated_at=updated_at)

	def set_data(
		self,
		pages: list[Page[TPage, TPageParam]]
		| Callable[
			[list[Page[TPage, TPageParam]] | None], list[Page[TPage, TPageParam]]
		],
		updated_at: float | dt.datetime | None = None,
	):
		"""Set pages manually, keeping has_next/prev in sync."""
		new_pages = pages(self.data.read()) if callable(pages) else pages
		self._set_success(new_pages, manual=True)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def set_error(
		self, error: Exception, *, updated_at: float | dt.datetime | None = None
	):
		self._set_error(error, manual=True)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def _set_success(
		self,
		pages: list[Page[TPage, TPageParam]],
		*,
		manual: bool = False,
	):
		self._update_has_more(pages)
		data = list(pages)
		self.data.write(data)
		self.last_updated.write(time.time())
		self.error.write(None)
		self.status.write("success")
		if not manual:
			self.fetch_status.write(cast(QueryFetchStatus, "idle"))
			self.retries.write(0)
			self.retry_reason.write(None)
		return data

	def _set_error(self, error: Exception, manual: bool = False):
		self.error.write(error)
		self.last_updated.write(time.time())
		self.status.write("error")
		if not manual:
			self.fetch_status.write(cast(QueryFetchStatus, "idle"))

	def _failed_retry(self, reason: Exception):
		self.retries.write(self.retries.read() + 1)
		self.retry_reason.write(reason)

	@property
	def effect(self) -> AsyncQueryEffect:
		if self._effect is None:
			self._effect = AsyncQueryEffect(
				self._run,
				fetcher=self,
				name=f"inf_query_effect({self.key})",
				deps=[] if self.key is not None else None,
			)
		return self._effect

	async def wait(self) -> list[Page[TPage, TPageParam]]:
		await self.effect.wait()
		return self.data.read() or []

	def observe(self, observer: Any):
		_ = self.effect  # ensure effect created
		self._observers.append(observer)
		self.cancel_gc()
		gc_time = getattr(observer, "_gc_time", 0)
		if gc_time and gc_time > 0:
			self.cfg.gc_time = max(self.cfg.gc_time, gc_time)

	def unobserve(self, observer: Any):
		if observer in self._observers:
			self._observers.remove(observer)
		if len(self._observers) == 0:
			self.schedule_gc()

	def invalidate(self, cancel_refetch: bool = False):
		should_schedule = not self.effect.is_scheduled or cancel_refetch
		if should_schedule and len(self._observers) > 0:
			self.effect.schedule()

	def schedule_gc(self):
		self.cancel_gc()
		if self.cfg.gc_time > 0:
			self._gc_handle = later(self.cfg.gc_time, self.dispose)
		else:
			self.dispose()

	def cancel_gc(self):
		if self._gc_handle:
			self._gc_handle.cancel()
			self._gc_handle = None

	def _compute_next_param(self) -> TPageParam | None:
		pages = self.data.read()
		if not pages or len(pages) == 0:
			return self.cfg.initial_page_param
		return self.cfg.get_next_page_param(pages)

	def _compute_previous_param(self) -> TPageParam | None:
		if self.cfg.get_previous_page_param is None:
			return None
		pages = self.data.read()
		if not pages or len(pages) == 0:
			return None
		return self.cfg.get_previous_page_param(pages)

	def _update_has_more(self, pages: list[Page[TPage, TPageParam]]):
		if len(pages) == 0:
			self.has_next_page.write(False)
			self.has_previous_page.write(self.cfg.get_previous_page_param is not None)
			return
		next_param = self.cfg.get_next_page_param(pages)
		prev_param = None
		if self.cfg.get_previous_page_param:
			prev_param = self.cfg.get_previous_page_param(pages)
		self.has_next_page.write(next_param is not None)
		self.has_previous_page.write(prev_param is not None)

	def _trim_if_needed(
		self,
		pages: list[Page[TPage, TPageParam]],
		direction: PageDirection,
	):
		if (
			self.cfg.max_pages
			and self.cfg.max_pages > 0
			and len(pages) > self.cfg.max_pages
		):
			over = len(pages) - self.cfg.max_pages
			if direction == "forward":
				pages[:] = pages[over:]
			else:
				pages[:] = pages[:-over]

	def _trim_to_max_pages_intelligently(
		self,
		pages: list[Page[TPage, TPageParam]],
		new_page_param: TPageParam,
	):
		"""Trim pages by removing the one furthest from the new page when max_pages exceeded."""
		if (
			self.cfg.max_pages
			and self.cfg.max_pages > 0
			and len(pages) > self.cfg.max_pages
		):
			over = len(pages) - self.cfg.max_pages

			for _ in range(over):
				furthest_idx = 0
				max_distance = 0

				if len(pages) > 0:
					furthest_idx = 0
					try:
						max_distance = abs(pages[0].param - new_page_param)  # type: ignore[operator,arg-type]
					except TypeError:
						max_distance = 0

					for i, page in enumerate(pages[1:], 1):
						try:
							distance = abs(page.param - new_page_param)  # type: ignore[operator,arg-type]
							if distance > max_distance:
								max_distance = distance
								furthest_idx = i
						except TypeError:
							try:
								new_idx = [p.param for p in pages].index(new_page_param)
								mid_point = len(pages) // 2
								furthest_idx = (
									len(pages) - 1 if new_idx < mid_point else 0
								)
							except ValueError:
								furthest_idx = len(pages) - 1
							break

				pages.pop(furthest_idx)

	async def _fetch_page_value(self, page_param: TPageParam) -> TPage:
		retries = 0
		while True:
			try:
				return await self.fn(page_param)
			except asyncio.CancelledError:
				raise
			except Exception as e:
				if retries < self.cfg.retries:
					retries += 1
					self._failed_retry(e)
					await asyncio.sleep(self.cfg.retry_delay)
					continue
				raise

	async def _initial_fetch(self):
		page = await self._fetch_page_value(self.cfg.initial_page_param)
		data = self._set_success([Page(page, self.cfg.initial_page_param)])
		for obs in self._observers:
			if getattr(obs, "_on_success", None):
				await maybe_await(call_flexible(obs._on_success, data))

	async def _refetch_existing(
		self,
		existing: list[Page[TPage, TPageParam]],
		refetch_page: Callable[[TPage, int, list[TPage]], bool] | None,
	):
		page_param: TPageParam = (
			existing[0].param if len(existing) > 0 else self.cfg.initial_page_param
		)

		new_pages: list[Page[TPage, TPageParam]] = []

		for idx, old_page in enumerate(existing):
			should_refetch = True
			if refetch_page is not None:
				should_refetch = bool(
					refetch_page(old_page.data, idx, [p.data for p in existing])
				)

			page = (
				await self._fetch_page_value(page_param)
				if should_refetch
				else old_page.data
			)

			new_pages.append(Page(page, page_param))

			next_param = self.cfg.get_next_page_param(new_pages)
			if next_param is None:
				break
			page_param = next_param

		self._trim_if_needed(new_pages, direction="forward")
		data = self._set_success(new_pages)
		for obs in self._observers:
			if getattr(obs, "_on_success", None):
				await maybe_await(call_flexible(obs._on_success, data))

	async def _run(self):
		# Reset retries at start of run
		self.retries.write(0)
		self.retry_reason.write(None)

		refetch_page = self._refetch_page
		self._refetch_page = None

		existing = self.data.read()
		if existing is None or len(existing) == 0:
			# Initial fetch with operation-level retries
			while True:
				try:
					await self._initial_fetch()
					return
				except asyncio.CancelledError:
					raise
				except Exception as e:
					current_retries = self.retries.read()
					if current_retries < self.cfg.retries:
						# Record failed retry attempt and retry
						self._failed_retry(e)
						# Wait before retrying
						await asyncio.sleep(self.cfg.retry_delay)
					else:
						# All retries exhausted - update retry_reason to final error
						self.retry_reason.write(e)
						self._set_error(e)
						for obs in self._observers:
							if getattr(obs, "_on_error", None):
								await maybe_await(call_flexible(obs._on_error, e))
						return
		else:
			# Refetch existing with operation-level retries
			while True:
				try:
					await self._refetch_existing(existing, refetch_page)
					return
				except asyncio.CancelledError:
					raise
				except Exception as e:
					current_retries = self.retries.read()
					if current_retries < self.cfg.retries:
						# Record failed retry attempt and retry
						self._failed_retry(e)
						# Wait before retrying
						await asyncio.sleep(self.cfg.retry_delay)
					else:
						# All retries exhausted - update retry_reason to final error
						self.retry_reason.write(e)
						self._set_error(e)
						for obs in self._observers:
							if getattr(obs, "_on_error", None):
								await maybe_await(call_flexible(obs._on_error, e))
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

	async def fetch_page(self, page_param: TPageParam):
		# Reset retries for this operation
		self.retries.write(0)
		self.retry_reason.write(None)

		while True:
			try:
				current_pages = list(self.data.read() or [])

				for idx, existing in enumerate(current_pages):
					if existing.param != page_param:
						continue
					page = await self._fetch_page_value(page_param)
					current_pages[idx] = Page(page, page_param)
					self._set_success(current_pages)
					return page

				page = await self._fetch_page_value(page_param)

				insertion_idx = 0
				try:
					for i, existing_page in enumerate(current_pages):
						if page_param < existing_page.param:
							insertion_idx = i
							break
					else:
						insertion_idx = len(current_pages)
				except TypeError:
					insertion_idx = len(current_pages)

				current_pages.insert(insertion_idx, Page(page, page_param))

				self._trim_to_max_pages_intelligently(current_pages, page_param)

				self._set_success(current_pages)
				return page
			except asyncio.CancelledError:
				raise
			except Exception as e:
				current_retries = self.retries.read()
				if current_retries < self.cfg.retries:
					# Record failed retry attempt and retry
					self._failed_retry(e)
					# Wait before retrying
					await asyncio.sleep(self.cfg.retry_delay)
				else:
					# All retries exhausted
					self.retry_reason.write(e)
					self._set_error(e)
					for obs in self._observers:
						if getattr(obs, "_on_error", None):
							await maybe_await(call_flexible(obs._on_error, e))
					return None

	async def _fetch_page(self, page_param: TPageParam, *, direction: PageDirection):
		retries = 0
		while True:
			try:
				page = await self.fn(page_param)
				current_pages = list(self.data.read() or [])
				for idx, existing in enumerate(current_pages):
					if existing.param == page_param:
						current_pages.pop(idx)
						break
				if direction == "forward":
					current_pages.append(Page(page, page_param))
				else:
					current_pages.insert(0, Page(page, page_param))

				self._trim_if_needed(current_pages, direction)
				data = self._set_success(current_pages)

				for obs in self._observers:
					if getattr(obs, "_on_success", None):
						await maybe_await(call_flexible(obs._on_success, data))
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
					if getattr(obs, "_on_error", None):
						await maybe_await(call_flexible(obs._on_error, e))
				raise

	async def refetch(
		self,
		cancel_refetch: bool = True,
		refetch_page: Callable[[TPage, int, list[TPage]], bool] | None = None,
	) -> list[Page[TPage, TPageParam]]:
		if cancel_refetch:
			self.effect.cancel()
		self._refetch_page = refetch_page
		try:
			await self.wait()
			return self.data.read() or []
		finally:
			self._refetch_page = None

	@override
	def dispose(self):
		if self._next_task and not self._next_task.done():
			self._next_task.cancel()
		if self._prev_task and not self._prev_task.done():
			self._prev_task.cancel()
		if self._effect:
			self._effect.dispose()
		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)


def none_if_missing(value: Any):
	return None if value is MISSING else value


class InfiniteQueryResult(Generic[TPage, TPageParam], Disposable):
	"""
	Observer wrapper for InfiniteQuery with lifecycle and stale tracking.
	"""

	_query: Computed[InfiniteQuery[TPage, TPageParam]]
	_stale_time: float
	_gc_time: float
	_keep_previous_data: bool
	_on_success: (
		Callable[[list[Page[TPage, TPageParam]]], Awaitable[None] | None] | None
	)
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_observe_effect: Effect
	_data_computed: Computed[list[Page[TPage, TPageParam]] | None]
	_enabled: Signal[bool]
	_fetch_on_mount: bool

	def __init__(
		self,
		query: Computed[InfiniteQuery[TPage, TPageParam]],
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		keep_previous_data: bool = False,
		on_success: Callable[[list[Page[TPage, TPageParam]]], Awaitable[None] | None]
		| None = None,
		on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
	):
		self._query = query
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._keep_previous_data = keep_previous_data
		self._on_success = on_success
		self._on_error = on_error
		self._enabled = Signal(enabled, name=f"inf_query.enabled({query().key})")
		self._fetch_on_mount = fetch_on_mount

		def observe_effect():
			q = self._query()
			enabled = self._enabled()
			with Untrack():
				q.observe(self)

			if enabled and fetch_on_mount and self.is_stale():
				q.invalidate()

			def cleanup():
				q.unobserve(self)

			return cleanup

		self._observe_effect = Effect(
			observe_effect,
			name=f"inf_query_observe({self._query().key})",
			immediate=True,
		)
		self._data_computed = Computed(
			self._data_computed_fn, name=f"inf_query_data({self._query().key})"
		)

	@property
	def status(self) -> QueryStatus:
		return self._query().status()

	@property
	def fetch_status(self) -> QueryFetchStatus:
		return self._query().fetch_status()

	@property
	def is_loading(self) -> bool:
		return self.status == "loading"

	@property
	def is_success(self) -> bool:
		return self.status == "success"

	@property
	def is_error(self) -> bool:
		return self.status == "error"

	@property
	def is_fetching(self) -> bool:
		return self.fetch_status == "fetching"

	@property
	def error(self) -> Exception | None:
		return self._query().error.read()

	def _data_computed_fn(
		self, prev: list[Page[TPage, TPageParam]] | None
	) -> list[Page[TPage, TPageParam]] | None:
		query = self._query()
		if self._keep_previous_data and query.status() != "success":
			return prev
		return query.data()

	@property
	def data(self) -> list[Page[TPage, TPageParam]] | None:
		return self._data_computed()

	@property
	def pages(self) -> list[TPage] | None:
		d = self.data
		return [p.data for p in d] if d else None

	@property
	def page_params(self) -> list[TPageParam] | None:
		d = self.data
		return [p.param for p in d] if d else None

	@property
	def has_next_page(self) -> bool:
		return self._query().has_next_page()

	@property
	def has_previous_page(self) -> bool:
		return self._query().has_previous_page()

	@property
	def is_fetching_next_page(self) -> bool:
		return self._query().is_fetching_next_page()

	@property
	def is_fetching_previous_page(self) -> bool:
		return self._query().is_fetching_previous_page()

	def is_stale(self) -> bool:
		if self._stale_time <= 0:
			return False
		query = self._query()
		return (time.time() - query.last_updated.read()) > self._stale_time

	async def fetch_next_page(self, page_param: TPageParam | None = None):
		return await self._query().fetch_next_page(page_param)

	async def fetch_previous_page(self, page_param: TPageParam | None = None):
		return await self._query().fetch_previous_page(page_param)

	async def fetch_page(self, page_param: TPageParam):
		return await self._query().fetch_page(page_param)

	def set_initial_data(
		self,
		pages: list[Page[TPage, TPageParam]]
		| Callable[[], list[Page[TPage, TPageParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		return self._query().set_initial_data(pages, updated_at=updated_at)

	def set_data(
		self,
		pages: list[Page[TPage, TPageParam]]
		| Callable[
			[list[Page[TPage, TPageParam]] | None], list[Page[TPage, TPageParam]]
		],
		updated_at: float | dt.datetime | None = None,
	):
		return self._query().set_data(pages, updated_at=updated_at)

	async def refetch(
		self,
		cancel_refetch: bool = True,
		refetch_page: Callable[[TPage, int, list[TPage]], bool] | None = None,
	) -> list[Page[TPage, TPageParam]]:
		return await self._query().refetch(
			cancel_refetch=cancel_refetch, refetch_page=refetch_page
		)

	async def wait(self) -> list[Page[TPage, TPageParam]]:
		return await self._query().wait()

	def invalidate(self):
		query = self._query()
		query.invalidate()

	def enable(self):
		self._enabled.write(True)

	def disable(self):
		self._enabled.write(False)

	def set_error(self, error: Exception):
		query = self._query()
		query.set_error(error)

	@override
	def dispose(self):
		self._observe_effect.dispose()


class InfiniteQueryProperty(Generic[TPage, TPageParam, TState], InitializableProperty):
	name: str
	_fetch_fn: "Callable[[TState, TPageParam], Awaitable[TPage]]"
	_keep_alive: bool
	_keep_previous_data: bool
	_stale_time: float
	_gc_time: float
	_retries: int
	_retry_delay: float
	_initial_page_param: TPageParam
	_get_next_page_param: (
		Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None] | None
	)
	_get_previous_page_param: (
		Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None] | None
	)
	_max_pages: int
	_key_fn: Callable[[TState], QueryKey] | None
	# Not using OnSuccessFn and OnErrorFn since unions of callables are not well
	# supported in the type system. We just need to be careful to use
	# call_flexible to invoke these functions.
	_on_success_fn: Callable[[TState, list[TPage]], Any] | None
	_on_error_fn: Callable[[TState, Exception], Any] | None
	_initial_data_updated_at: float | dt.datetime | None
	_enabled: bool
	_fetch_on_mount: bool
	_priv_result: str

	def __init__(
		self,
		name: str,
		fetch_fn: "Callable[[TState, TPageParam], Awaitable[TPage]]",
		*,
		initial_page_param: TPageParam,
		max_pages: int,
		stale_time: float,
		gc_time: float,
		keep_previous_data: bool,
		retries: int,
		retry_delay: float,
		initial_data_updated_at: float | dt.datetime | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
	):
		self.name = name
		self._fetch_fn = fetch_fn
		self._initial_page_param = initial_page_param
		self._get_next_page_param = None
		self._get_previous_page_param = None
		self._max_pages = max_pages
		self._keep_previous_data = keep_previous_data
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._retries = retries
		self._retry_delay = retry_delay
		self._on_success_fn = None
		self._on_error_fn = None
		self._key_fn = None
		self._initial_data_updated_at = initial_data_updated_at
		self._enabled = enabled
		self._fetch_on_mount = fetch_on_mount
		self._priv_result = f"__inf_query_{name}"

	def key(self, fn: Callable[[TState], QueryKey]):
		if self._key_fn is not None:
			raise RuntimeError(
				f"Duplicate key() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._key_fn = fn
		return fn

	def on_success(self, fn: OnSuccessFn[TState, list[TPage]]):
		if self._on_success_fn is not None:
			raise RuntimeError(
				f"Duplicate on_success() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._on_success_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	def on_error(self, fn: OnErrorFn[TState]):
		if self._on_error_fn is not None:
			raise RuntimeError(
				f"Duplicate on_error() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._on_error_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	def get_next_page_param(
		self,
		fn: Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None],
	) -> Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None]:
		if self._get_next_page_param is not None:
			raise RuntimeError(
				f"Duplicate get_next_page_param() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._get_next_page_param = fn
		return fn

	def get_previous_page_param(
		self,
		fn: Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None],
	) -> Callable[[TState, list[Page[TPage, TPageParam]]], TPageParam | None]:
		if self._get_previous_page_param is not None:
			raise RuntimeError(
				f"Duplicate get_previous_page_param() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._get_previous_page_param = fn
		return fn

	@override
	def initialize(
		self, state: Any, name: str
	) -> InfiniteQueryResult[TPage, TPageParam]:
		result: InfiniteQueryResult[TPage, TPageParam] | None = getattr(
			state, self._priv_result, None
		)
		if result:
			return result

		if self._get_next_page_param is None:
			raise RuntimeError(
				f"get_next_page_param must be set via @{self.name}.get_next_page_param decorator"
			)

		fetch_fn = bind_state(state, self._fetch_fn)

		next_fn = bind_state(state, self._get_next_page_param)
		prev_fn = (
			bind_state(state, self._get_previous_page_param)
			if self._get_previous_page_param
			else None
		)

		if self._key_fn:
			query = self._resolve_keyed(
				state, fetch_fn, next_fn, prev_fn, self._initial_data_updated_at
			)
		else:
			query = self._resolve_unkeyed(
				fetch_fn, next_fn, prev_fn, self._initial_data_updated_at
			)

		on_success = None
		if self._on_success_fn:
			bound_fn = bind_state(state, self._on_success_fn)

			async def on_success_wrapper(data: list[Page[TPage, TPageParam]]):
				await maybe_await(call_flexible(bound_fn, [p.data for p in data]))

			on_success = on_success_wrapper

		result = InfiniteQueryResult(
			query=query,
			stale_time=self._stale_time,
			keep_previous_data=self._keep_previous_data,
			gc_time=self._gc_time,
			on_success=on_success,
			on_error=bind_state(state, self._on_error_fn)
			if self._on_error_fn
			else None,
			enabled=self._enabled,
			fetch_on_mount=self._fetch_on_mount,
		)

		setattr(state, self._priv_result, result)
		return result

	def _resolve_keyed(
		self,
		state: TState,
		fetch_fn: Callable[[TPageParam], Awaitable[TPage]],
		next_fn: Callable[[list[Page[TPage, TPageParam]]], TPageParam | None],
		prev_fn: Callable[[list[Page[TPage, TPageParam]]], TPageParam | None] | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> Computed[InfiniteQuery[TPage, TPageParam]]:
		assert self._key_fn is not None
		key_computed = Computed(
			bind_state(state, self._key_fn), name=f"inf_query.key.{self.name}"
		)
		render = PulseContext.get().render
		if render is None:
			raise RuntimeError("No render session available")
		store = render.query_store

		def query() -> InfiniteQuery[TPage, TPageParam]:
			key = key_computed()
			return cast(
				InfiniteQuery[TPage, TPageParam],
				store.ensure_infinite(
					key,
					fetch_fn,
					initial_page_param=self._initial_page_param,
					get_next_page_param=next_fn,
					get_previous_page_param=prev_fn,
					max_pages=self._max_pages,
					gc_time=self._gc_time,
					retries=self._retries,
					retry_delay=self._retry_delay,
					initial_data_updated_at=initial_data_updated_at,
				),
			)

		return Computed(query, name=f"inf_query.{self.name}")

	def _resolve_unkeyed(
		self,
		fetch_fn: Callable[[TPageParam], Awaitable[TPage]],
		next_fn: Callable[[list[Page[TPage, TPageParam]]], TPageParam | None],
		prev_fn: Callable[[list[Page[TPage, TPageParam]]], TPageParam | None] | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> Computed[InfiniteQuery[TPage, TPageParam]]:
		query = InfiniteQuery[TPage, TPageParam](
			None,
			fetch_fn,
			initial_page_param=self._initial_page_param,
			get_next_page_param=next_fn,
			get_previous_page_param=prev_fn,
			max_pages=self._max_pages,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=self._gc_time,
			retries=self._retries,
			retry_delay=self._retry_delay,
		)
		return Computed(lambda: query, name=f"inf_query.{self.name}")

	def __get__(
		self, obj: Any, objtype: Any = None
	) -> InfiniteQueryResult[TPage, TPageParam]:
		if obj is None:
			return self  # pyright: ignore[reportReturnType]
		return self.initialize(obj, self.name)
