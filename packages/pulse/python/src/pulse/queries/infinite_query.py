import asyncio
import datetime as dt
import inspect
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import (
	Any,
	Generic,
	NamedTuple,
	TypeVar,
	cast,
	overload,
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
	ActionError,
	ActionResult,
	ActionSuccess,
	OnErrorFn,
	OnSuccessFn,
	QueryKey,
	QueryStatus,
	bind_state,
)
from pulse.queries.query import RETRY_DELAY_DEFAULT, QueryConfig
from pulse.reactive import Computed, Effect, Signal, Untrack
from pulse.reactive_extensions import ReactiveList, unwrap
from pulse.state import InitializableProperty, State

T = TypeVar("T")
TParam = TypeVar("TParam")
TState = TypeVar("TState", bound=State)


class Page(NamedTuple, Generic[T, TParam]):
	data: T
	param: TParam


# ─────────────────────────────────────────────────────────────────────────────
# Action types for the task queue (pure data)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FetchNext(Generic[T, TParam]):
	"""Fetch the next page."""

	future: "asyncio.Future[ActionResult[Page[T, TParam] | None]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class FetchPrevious(Generic[T, TParam]):
	"""Fetch the previous page."""

	future: "asyncio.Future[ActionResult[Page[T, TParam] | None]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class Refetch(Generic[T, TParam]):
	"""Refetch all pages."""

	refetch_page: Callable[[T, int, list[T]], bool] | None = None
	future: "asyncio.Future[ActionResult[list[Page[T, TParam]]]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class RefetchPage(Generic[T, TParam]):
	"""Refetch a single page by param."""

	param: TParam
	future: "asyncio.Future[ActionResult[T | None]]" = field(
		default_factory=asyncio.Future
	)


Action = (
	FetchNext[T, TParam]
	| FetchPrevious[T, TParam]
	| Refetch[T, TParam]
	| RefetchPage[T, TParam]
)


@dataclass(slots=True)
class InfiniteQueryConfig(QueryConfig[list[Page[T, TParam]]], Generic[T, TParam]):
	"""Configuration for InfiniteQuery. Contains all QueryConfig fields plus infinite query specific options."""

	initial_page_param: TParam
	get_next_page_param: Callable[[list[Page[T, TParam]]], TParam | None]
	get_previous_page_param: Callable[[list[Page[T, TParam]]], TParam | None] | None
	max_pages: int


class InfiniteQuery(Generic[T, TParam], Disposable):
	"""Paginated query that stores data as a list of Page(data, param)."""

	key: QueryKey
	fn: Callable[[TParam], Awaitable[T]]
	cfg: InfiniteQueryConfig[T, TParam]

	# Reactive state
	pages: ReactiveList[Page[T, TParam]]
	error: Signal[Exception | None]
	last_updated: Signal[float]
	status: Signal[QueryStatus]
	is_fetching: Signal[bool]
	retries: Signal[int]
	retry_reason: Signal[Exception | None]

	has_next_page: Signal[bool]
	has_previous_page: Signal[bool]
	current_action: "Signal[Action[T, TParam] | None]"

	# Task queue
	_queue: deque[Action[T, TParam]]
	_queue_task: asyncio.Task[None] | None

	_observers: "list[InfiniteQueryResult[T, TParam]]"
	_gc_handle: asyncio.TimerHandle | None

	def __init__(
		self,
		key: QueryKey,
		fn: Callable[[TParam], Awaitable[T]],
		*,
		initial_page_param: TParam,
		get_next_page_param: Callable[[list[Page[T, TParam]]], TParam | None],
		get_previous_page_param: (
			Callable[[list[Page[T, TParam]]], TParam | None] | None
		) = None,
		max_pages: int = 0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: list[Page[T, TParam]] | None | Any = MISSING,
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

		initial_pages: list[Page[T, TParam]]
		if initial_data is MISSING:
			initial_pages = []
		else:
			initial_pages = cast(list[Page[T, TParam]], initial_data) or []

		self.pages = ReactiveList(initial_pages)
		self.error = Signal(None, name=f"inf_query.error({key})")
		self.last_updated = Signal(0.0, name=f"inf_query.last_updated({key})")
		if initial_data_updated_at:
			self.set_updated_at(initial_data_updated_at)

		self.status = Signal(
			"loading" if len(initial_pages) == 0 else "success",
			name=f"inf_query.status({key})",
		)
		self.is_fetching = Signal(False, name=f"inf_query.is_fetching({key})")
		self.retries = Signal(0, name=f"inf_query.retries({key})")
		self.retry_reason = Signal(None, name=f"inf_query.retry_reason({key})")

		self.has_next_page = Signal(False, name=f"inf_query.has_next({key})")
		self.has_previous_page = Signal(False, name=f"inf_query.has_prev({key})")
		self.current_action = Signal(None, name=f"inf_query.current_action({key})")

		self._queue = deque()
		self._queue_task = None
		self._observers = []
		self._gc_handle = None

	# ─────────────────────────────────────────────────────────────────────────
	# Commit functions - update state after pages have been modified
	# ─────────────────────────────────────────────────────────────────────────

	async def commit(self):
		"""Commit current pages state and run success callbacks."""
		self._commit_sync()

		for obs in self._observers:
			if obs._on_success is not None:  # pyright: ignore[reportPrivateUsage]
				await maybe_await(call_flexible(obs._on_success, self.pages))  # pyright: ignore[reportPrivateUsage]

	async def _commit_error(self, error: Exception):
		"""Commit error state and run error callbacks."""
		self._commit_error_sync(error)

		for obs in self._observers:
			if obs._on_error is not None:  # pyright: ignore[reportPrivateUsage]
				await maybe_await(call_flexible(obs._on_error, error))  # pyright: ignore[reportPrivateUsage]

	def _commit_sync(self):
		"""Synchronous commit - updates state based on current pages."""
		self._update_has_more()
		self.last_updated.write(time.time())
		self.error.write(None)
		self.status.write("success")
		self.retries.write(0)
		self.retry_reason.write(None)

	def _commit_error_sync(self, error: Exception):
		"""Synchronous error commit for set_error (no callbacks)."""
		self.error.write(error)
		self.last_updated.write(time.time())
		self.status.write("error")
		self.is_fetching.write(False)

	def _record_retry(self, reason: Exception):
		"""Record a failed retry attempt."""
		self.retries.write(self.retries.read() + 1)
		self.retry_reason.write(reason)

	def _reset_retries(self):
		"""Reset retry state at start of operation."""
		self.retries.write(0)
		self.retry_reason.write(None)

	# ─────────────────────────────────────────────────────────────────────────
	# Public API
	# ─────────────────────────────────────────────────────────────────────────

	def set_updated_at(self, updated_at: float | dt.datetime):
		if isinstance(updated_at, dt.datetime):
			updated_at = updated_at.timestamp()
		self.last_updated.write(updated_at)

	def set_initial_data(
		self,
		pages: list[Page[T, TParam]] | Callable[[], list[Page[T, TParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		"""Set initial pages while the query is still loading."""
		if self.status() != "loading":
			return
		value = pages() if callable(pages) else pages
		self.set_data(value, updated_at=updated_at)

	def set_data(
		self,
		pages: list[Page[T, TParam]]
		| Callable[[list[Page[T, TParam]]], list[Page[T, TParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		"""Set pages manually, keeping has_next/prev in sync."""
		new_pages = pages(self.pages) if callable(pages) else pages
		self.pages.clear()
		self.pages.extend(new_pages)
		self._trim_back()
		self._commit_sync()
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def set_error(
		self, error: Exception, *, updated_at: float | dt.datetime | None = None
	):
		self._commit_error_sync(error)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	async def wait(self) -> ActionResult[list[Page[T, TParam]]]:
		"""Wait for initial data or until queue is empty."""
		# If no data and loading, enqueue initial fetch (unless already processing)
		if len(self.pages) == 0 and self.status() == "loading":
			if self._queue_task is None or self._queue_task.done():
				self._enqueue(Refetch())
		# Wait for any in-progress queue processing
		if self._queue_task and not self._queue_task.done():
			await self._queue_task
		# Return result based on current state
		if self.status() == "error":
			return ActionError(cast(Exception, self.error()))
		return ActionSuccess(list(self.pages))

	def observe(self, observer: Any):
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

	def invalidate(
		self,
		*,
		cancel_fetch: bool = False,
		refetch_page: Callable[[T, int, list[T]], bool] | None = None,
	):
		"""Enqueue a refetch. Synchronous - does not wait for completion."""
		if cancel_fetch:
			self._cancel_queue()
		if len(self._observers) > 0:
			self._enqueue(Refetch(refetch_page=refetch_page))

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

	# ─────────────────────────────────────────────────────────────────────────
	# Page param computation
	# ─────────────────────────────────────────────────────────────────────────

	def compute_next_param(self) -> TParam | None:
		if len(self.pages) == 0:
			return self.cfg.initial_page_param
		return self.cfg.get_next_page_param(self.pages)

	def compute_previous_param(self) -> TParam | None:
		if self.cfg.get_previous_page_param is None:
			return None
		if len(self.pages) == 0:
			return None
		return self.cfg.get_previous_page_param(self.pages)

	def _update_has_more(self):
		if len(self.pages) == 0:
			self.has_next_page.write(False)
			self.has_previous_page.write(self.cfg.get_previous_page_param is not None)
			return
		next_param = self.cfg.get_next_page_param(self.pages)
		prev_param = None
		if self.cfg.get_previous_page_param:
			prev_param = self.cfg.get_previous_page_param(self.pages)
		self.has_next_page.write(next_param is not None)
		self.has_previous_page.write(prev_param is not None)

	# ─────────────────────────────────────────────────────────────────────────
	# Trimming helpers
	# ─────────────────────────────────────────────────────────────────────────

	def _trim_front(self):
		"""Trim pages from front when over max_pages."""
		if self.cfg.max_pages and self.cfg.max_pages > 0:
			while len(self.pages) > self.cfg.max_pages:
				self.pages.pop(0)

	def _trim_back(self):
		"""Trim pages from back when over max_pages."""
		if self.cfg.max_pages and self.cfg.max_pages > 0:
			while len(self.pages) > self.cfg.max_pages:
				self.pages.pop()

	# ─────────────────────────────────────────────────────────────────────────
	# Task Queue
	# ─────────────────────────────────────────────────────────────────────────

	def _cancel_queue(self):
		"""Cancel all pending actions in the queue."""
		while self._queue:
			action = self._queue.popleft()
			if not action.future.done():
				action.future.cancel()

	def _enqueue(
		self,
		action: "FetchNext[T, TParam] | FetchPrevious[T, TParam] | Refetch[T, TParam] | RefetchPage[T, TParam]",
		*,
		cancel_fetch: bool = False,
	) -> asyncio.Future[Any]:
		"""Enqueue an action and ensure the processor is running."""
		if cancel_fetch:
			self._cancel_queue()

		self._queue.append(action)
		self._ensure_processor()
		return action.future

	def _ensure_processor(self):
		"""Ensure the queue processor task is running."""
		if self._queue_task is None or self._queue_task.done():
			# Create task with no reactive scope to avoid inheriting deps from caller
			with Untrack():
				self._queue_task = asyncio.create_task(self._process_queue())
		return self._queue_task

	async def _process_queue(self):
		"""Process queued actions sequentially with retry logic."""
		while self._queue:
			action = self._queue.popleft()

			if action.future.cancelled():
				continue

			# Reset state for new action
			self._reset_retries()
			self.is_fetching.write(True)
			self.current_action.write(action)

			try:
				while True:
					try:
						result = await self._execute_action(action)
						if not action.future.done():
							action.future.set_result(ActionSuccess(result))
						break
					except asyncio.CancelledError:
						raise
					except Exception as e:
						if self.retries.read() < self.cfg.retries:
							self._record_retry(e)
							await asyncio.sleep(self.cfg.retry_delay)
							continue
						raise
			except asyncio.CancelledError:
				if not action.future.done():
					action.future.cancel()
				raise
			except Exception as e:
				self.retry_reason.write(e)
				await self._commit_error(e)
				if not action.future.done():
					action.future.set_result(ActionError(e))
			finally:
				self.is_fetching.write(False)
				self.current_action.write(None)

	async def _execute_action(
		self,
		action: "FetchNext[T, TParam] | FetchPrevious[T, TParam] | Refetch[T, TParam] | RefetchPage[T, TParam]",
	) -> Any:
		"""Execute a single action."""
		if isinstance(action, FetchNext):
			return await self._execute_fetch_next(action)
		elif isinstance(action, FetchPrevious):
			return await self._execute_fetch_previous(action)
		elif isinstance(action, Refetch):
			return await self._execute_refetch_all(action)
		elif isinstance(action, RefetchPage):
			return await self._execute_refetch_one(action)
		else:
			raise TypeError(f"Unknown action type: {type(action)}")

	async def _execute_fetch_next(
		self, action: "FetchNext[T, TParam]"
	) -> Page[T, TParam] | None:
		next_param = self.compute_next_param()
		if next_param is None:
			self.has_next_page.write(False)
			return None

		page = await self.fn(next_param)
		page = Page(page, next_param)
		self.pages.append(page)
		self._trim_front()
		await self.commit()
		return page

	async def _execute_fetch_previous(
		self, action: "FetchPrevious[T, TParam]"
	) -> Page[T, TParam] | None:
		prev_param = self.compute_previous_param()
		if prev_param is None:
			self.has_previous_page.write(False)
			return None

		data = await self.fn(prev_param)
		page = Page(data, prev_param)
		self.pages.insert(0, page)
		self._trim_back()
		await self.commit()
		return page

	async def _execute_refetch_all(
		self, action: "Refetch[T, TParam]"
	) -> list[Page[T, TParam]]:
		if len(self.pages) == 0:
			print("performing initial fetch in refetch_all")
			page = await self.fn(self.cfg.initial_page_param)
			self.pages.append(Page(page, self.cfg.initial_page_param))
			await self.commit()
			return self.pages

		page_param: TParam = self.pages[0].param
		num_existing = len(self.pages)

		for idx in range(num_existing):
			old_page = self.pages[idx]
			should_refetch = True
			if action.refetch_page is not None:
				should_refetch = bool(
					action.refetch_page(
						old_page.data, idx, [p.data for p in self.pages]
					)
				)

			if should_refetch:
				print(f"Refeching page {page_param}")
				page = await self.fn(page_param)
				print("Result:", page)
			else:
				page = old_page.data
			self.pages[idx] = Page(page, page_param)

			next_param = self.cfg.get_next_page_param(self.pages[: idx + 1])
			if next_param is None:
				# Trim remaining pages if we ended early
				while len(self.pages) > idx + 1:
					self.pages.pop()
				break
			page_param = next_param

		await self.commit()
		return self.pages

	async def _execute_refetch_one(self, action: "RefetchPage[T, TParam]") -> T | None:
		idx = next(
			(i for i, p in enumerate(self.pages) if p.param == action.param),
			None,
		)
		if idx is None:
			return None

		page = await self.fn(action.param)
		self.pages[idx] = Page(page, action.param)
		await self.commit()
		return page

	# ─────────────────────────────────────────────────────────────────────────
	# Public fetch API
	# ─────────────────────────────────────────────────────────────────────────

	async def fetch_next_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		"""Fetch the next page. Queued for sequential execution."""
		action: FetchNext[T, TParam] = FetchNext()
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def fetch_previous_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		"""Fetch the previous page. Queued for sequential execution."""
		action: FetchPrevious[T, TParam] = FetchPrevious()
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def refetch(
		self,
		*,
		cancel_fetch: bool = False,
		refetch_page: Callable[[T, int, list[T]], bool] | None = None,
	) -> ActionResult[list[Page[T, TParam]]]:
		"""Refetch all pages. Queued for sequential execution."""
		action: Refetch[T, TParam] = Refetch(refetch_page=refetch_page)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def refetch_page(
		self,
		param: TParam,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[T | None]:
		"""Refetch an existing page by its param. Queued for sequential execution."""
		action: RefetchPage[T, TParam] = RefetchPage(param=param)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	@override
	def dispose(self):
		self._cancel_queue()
		if self._queue_task and not self._queue_task.done():
			self._queue_task.cancel()
		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)


def none_if_missing(value: Any):
	return None if value is MISSING else value


class InfiniteQueryResult(Generic[T, TParam], Disposable):
	"""
	Observer wrapper for InfiniteQuery with lifecycle and stale tracking.
	"""

	_query: Computed[InfiniteQuery[T, TParam]]
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_keep_previous_data: bool
	_on_success: Callable[[list[Page[T, TParam]]], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_observe_effect: Effect
	_interval_effect: Effect | None
	_data_computed: Computed[list[Page[T, TParam]] | None]
	_enabled: Signal[bool]
	_fetch_on_mount: bool

	def __init__(
		self,
		query: Computed[InfiniteQuery[T, TParam]],
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		refetch_interval: float | None = None,
		keep_previous_data: bool = False,
		on_success: Callable[[list[Page[T, TParam]]], Awaitable[None] | None]
		| None = None,
		on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
	):
		self._query = query
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._refetch_interval = refetch_interval
		self._keep_previous_data = keep_previous_data
		self._on_success = on_success
		self._on_error = on_error
		self._enabled = Signal(enabled, name=f"inf_query.enabled({query().key})")
		self._fetch_on_mount = fetch_on_mount
		self._interval_effect = None

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

		# Set up interval effect if interval is specified
		if refetch_interval is not None and refetch_interval > 0:
			self._setup_interval_effect(refetch_interval)

	def _setup_interval_effect(self, interval: float):
		"""Create an effect that invalidates the query at the specified interval."""

		def interval_fn():
			# Read enabled to make this effect reactive to enabled changes
			if self._enabled():
				self._query().invalidate()

		self._interval_effect = Effect(
			interval_fn,
			name=f"inf_query_interval({self._query().key})",
			interval=interval,
			immediate=True,
		)

	@property
	def status(self) -> QueryStatus:
		return self._query().status()

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
		return self._query().is_fetching()

	@property
	def error(self) -> Exception | None:
		return self._query().error.read()

	def _data_computed_fn(
		self, prev: list[Page[T, TParam]] | None
	) -> list[Page[T, TParam]] | None:
		query = self._query()
		if self._keep_previous_data and query.status() != "success":
			return prev
		# Access pages.version to subscribe to structural changes
		result = unwrap(query.pages) if len(query.pages) > 0 else None
		print("Computed data:", result)
		return result

	@property
	def data(self) -> list[Page[T, TParam]] | None:
		return self._data_computed()

	@property
	def pages(self) -> list[T] | None:
		d = self.data
		return [p.data for p in d] if d else None

	@property
	def page_params(self) -> list[TParam] | None:
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
		return isinstance(self._query().current_action(), FetchNext)

	@property
	def is_fetching_previous_page(self) -> bool:
		return isinstance(self._query().current_action(), FetchPrevious)

	def is_stale(self) -> bool:
		if self._stale_time <= 0:
			return False
		query = self._query()
		return (time.time() - query.last_updated.read()) > self._stale_time

	async def fetch_next_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		return await self._query().fetch_next_page(cancel_fetch=cancel_fetch)

	async def fetch_previous_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		return await self._query().fetch_previous_page(cancel_fetch=cancel_fetch)

	async def fetch_page(
		self,
		page_param: TParam,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[T | None]:
		return await self._query().refetch_page(page_param, cancel_fetch=cancel_fetch)

	def set_initial_data(
		self,
		pages: list[Page[T, TParam]] | Callable[[], list[Page[T, TParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		return self._query().set_initial_data(pages, updated_at=updated_at)

	def set_data(
		self,
		pages: list[Page[T, TParam]]
		| Callable[[list[Page[T, TParam]] | None], list[Page[T, TParam]]],
		updated_at: float | dt.datetime | None = None,
	):
		return self._query().set_data(pages, updated_at=updated_at)

	async def refetch(
		self,
		*,
		cancel_fetch: bool = False,
		refetch_page: Callable[[T, int, list[T]], bool] | None = None,
	) -> ActionResult[list[Page[T, TParam]]]:
		return await self._query().refetch(
			cancel_fetch=cancel_fetch, refetch_page=refetch_page
		)

	async def wait(self) -> ActionResult[list[Page[T, TParam]]]:
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
		if self._interval_effect is not None:
			self._interval_effect.dispose()
		self._observe_effect.dispose()


class InfiniteQueryProperty(Generic[T, TParam, TState], InitializableProperty):
	name: str
	_fetch_fn: "Callable[[TState, TParam], Awaitable[T]]"
	_keep_alive: bool
	_keep_previous_data: bool
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_retries: int
	_retry_delay: float
	_initial_page_param: TParam
	_get_next_page_param: (
		Callable[[TState, list[Page[T, TParam]]], TParam | None] | None
	)
	_get_previous_page_param: (
		Callable[[TState, list[Page[T, TParam]]], TParam | None] | None
	)
	_max_pages: int
	_key: QueryKey | Callable[[TState], QueryKey] | None
	# Not using OnSuccessFn and OnErrorFn since unions of callables are not well
	# supported in the type system. We just need to be careful to use
	# call_flexible to invoke these functions.
	_on_success_fn: Callable[[TState, list[T]], Any] | None
	_on_error_fn: Callable[[TState, Exception], Any] | None
	_initial_data_updated_at: float | dt.datetime | None
	_enabled: bool
	_fetch_on_mount: bool
	_priv_result: str

	def __init__(
		self,
		name: str,
		fetch_fn: "Callable[[TState, TParam], Awaitable[T]]",
		*,
		initial_page_param: TParam,
		max_pages: int,
		stale_time: float,
		gc_time: float,
		refetch_interval: float | None = None,
		keep_previous_data: bool,
		retries: int,
		retry_delay: float,
		initial_data_updated_at: float | dt.datetime | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
		key: QueryKey | Callable[[TState], QueryKey] | None = None,
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
		self._refetch_interval = refetch_interval
		self._retries = retries
		self._retry_delay = retry_delay
		self._on_success_fn = None
		self._on_error_fn = None
		self._key = key
		self._initial_data_updated_at = initial_data_updated_at
		self._enabled = enabled
		self._fetch_on_mount = fetch_on_mount
		self._priv_result = f"__inf_query_{name}"

	def key(self, fn: Callable[[TState], QueryKey]):
		if self._key is not None:
			raise RuntimeError(
				f"Cannot use @{self.name}.key decorator when a key is already provided to @infinite_query(key=...)."
			)
		self._key = fn
		return fn

	def on_success(self, fn: OnSuccessFn[TState, list[T]]):
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
		fn: Callable[[TState, list[Page[T, TParam]]], TParam | None],
	) -> Callable[[TState, list[Page[T, TParam]]], TParam | None]:
		if self._get_next_page_param is not None:
			raise RuntimeError(
				f"Duplicate get_next_page_param() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._get_next_page_param = fn
		return fn

	def get_previous_page_param(
		self,
		fn: Callable[[TState, list[Page[T, TParam]]], TParam | None],
	) -> Callable[[TState, list[Page[T, TParam]]], TParam | None]:
		if self._get_previous_page_param is not None:
			raise RuntimeError(
				f"Duplicate get_previous_page_param() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._get_previous_page_param = fn
		return fn

	@override
	def initialize(self, state: Any, name: str) -> InfiniteQueryResult[T, TParam]:
		result: InfiniteQueryResult[T, TParam] | None = getattr(
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

		if self._key is None:
			raise RuntimeError(
				f"key is required for infinite query '{self.name}'. Provide a key via @infinite_query(key=...) or @{self.name}.key decorator."
			)
		query = self._resolve_keyed(
			state, fetch_fn, next_fn, prev_fn, self._initial_data_updated_at
		)

		on_success = None
		if self._on_success_fn:
			bound_fn = bind_state(state, self._on_success_fn)

			async def on_success_wrapper(data: list[Page[T, TParam]]):
				await maybe_await(call_flexible(bound_fn, [p.data for p in data]))

			on_success = on_success_wrapper

		result = InfiniteQueryResult(
			query=query,
			stale_time=self._stale_time,
			keep_previous_data=self._keep_previous_data,
			gc_time=self._gc_time,
			refetch_interval=self._refetch_interval,
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
		fetch_fn: Callable[[TParam], Awaitable[T]],
		next_fn: Callable[[list[Page[T, TParam]]], TParam | None],
		prev_fn: Callable[[list[Page[T, TParam]]], TParam | None] | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> Computed[InfiniteQuery[T, TParam]]:
		assert self._key is not None

		# Create a Computed for the key - passthrough for constant keys, reactive for function keys
		if callable(self._key):
			key_computed = Computed(
				bind_state(state, self._key), name=f"inf_query.key.{self.name}"
			)
		else:
			constant_key = self._key  # ensure a constant reference
			key_computed = Computed(
				lambda: constant_key, name=f"inf_query.key.{self.name}"
			)

		render = PulseContext.get().render
		if render is None:
			raise RuntimeError("No render session available")
		store = render.query_store

		def query() -> InfiniteQuery[T, TParam]:
			key = key_computed()
			return cast(
				InfiniteQuery[T, TParam],
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

	def __get__(self, obj: Any, objtype: Any = None) -> InfiniteQueryResult[T, TParam]:
		if obj is None:
			return self  # pyright: ignore[reportReturnType]
		return self.initialize(obj, self.name)


@overload
def infinite_query(
	fn: Callable[[TState, TParam], Awaitable[T]],
	*,
	initial_page_param: TParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
) -> InfiniteQueryProperty[T, TParam, TState]: ...


@overload
def infinite_query(
	fn: None = None,
	*,
	initial_page_param: TParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
) -> Callable[
	[Callable[[TState, Any], Awaitable[T]]],
	InfiniteQueryProperty[T, TParam, TState],
]: ...


def infinite_query(
	fn: Callable[[TState, TParam], Awaitable[T]] | None = None,
	*,
	initial_page_param: TParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
):
	def decorator(
		func: Callable[[TState, TParam], Awaitable[T]], /
	) -> InfiniteQueryProperty[T, TParam, TState]:
		sig = inspect.signature(func)
		params = list(sig.parameters.values())
		if not (len(params) == 2 and params[0].name == "self"):
			raise TypeError(
				"@infinite_query must be applied to a state method with signature (self, page_param)"
			)

		return InfiniteQueryProperty(
			func.__name__,
			func,
			initial_page_param=initial_page_param,
			max_pages=max_pages,
			stale_time=stale_time,
			gc_time=gc_time if gc_time is not None else 300.0,
			refetch_interval=refetch_interval,
			keep_previous_data=keep_previous_data,
			retries=retries,
			retry_delay=RETRY_DELAY_DEFAULT if retry_delay is None else retry_delay,
			initial_data_updated_at=initial_data_updated_at,
			enabled=enabled,
			fetch_on_mount=fetch_on_mount,
			key=key,
		)

	if fn:
		return decorator(fn)
	return decorator
