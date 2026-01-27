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
	Missing,
	call_flexible,
	maybe_await,
)
from pulse.queries.common import (
	ActionError,
	ActionResult,
	ActionSuccess,
	Key,
	OnErrorFn,
	OnSuccessFn,
	QueryKey,
	QueryStatus,
	bind_state,
	normalize_key,
)
from pulse.queries.query import RETRY_DELAY_DEFAULT, QueryConfig
from pulse.reactive import Computed, Effect, Signal, Untrack
from pulse.reactive_extensions import ReactiveList, unwrap
from pulse.scheduling import TimerHandleLike, create_task, later
from pulse.state import InitializableProperty, State

T = TypeVar("T")
TParam = TypeVar("TParam")
TState = TypeVar("TState", bound=State)


class Page(NamedTuple, Generic[T, TParam]):
	"""Named tuple representing a page in an infinite query.

	Each page contains the fetched data and the parameter used to fetch it,
	enabling cursor-based or offset-based pagination.

	Attributes:
		data: The fetched page data of type T.
		param: The page parameter (cursor, offset, etc.) used to fetch this page.

	Example:

	```python
	# Access pages from infinite query result
	for page in state.posts.data:
	    print(f"Page param: {page.param}")
	    for post in page.data:
	        print(post.title)
	```
	"""

	data: T
	param: TParam


# ─────────────────────────────────────────────────────────────────────────────
# Action types for the task queue (pure data)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FetchNext(Generic[T, TParam]):
	"""Fetch the next page."""

	fetch_fn: Callable[[TParam], Awaitable[T]]
	observer: "InfiniteQueryResult[T, TParam] | None" = None
	future: "asyncio.Future[ActionResult[Page[T, TParam] | None]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class FetchPrevious(Generic[T, TParam]):
	"""Fetch the previous page."""

	fetch_fn: Callable[[TParam], Awaitable[T]]
	observer: "InfiniteQueryResult[T, TParam] | None" = None
	future: "asyncio.Future[ActionResult[Page[T, TParam] | None]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class Refetch(Generic[T, TParam]):
	"""Refetch all pages."""

	fetch_fn: Callable[[TParam], Awaitable[T]]
	observer: "InfiniteQueryResult[T, TParam] | None" = None
	refetch_page: Callable[[T, int, list[T]], bool] | None = None
	future: "asyncio.Future[ActionResult[list[Page[T, TParam]]]]" = field(
		default_factory=asyncio.Future
	)


@dataclass
class RefetchPage(Generic[T, TParam]):
	"""Refetch a single page by param."""

	fetch_fn: Callable[[TParam], Awaitable[T]]
	param: TParam
	observer: "InfiniteQueryResult[T, TParam] | None" = None
	clear: bool = False
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

	key: Key
	cfg: InfiniteQueryConfig[T, TParam]

	@property
	def fn(self) -> Callable[[TParam], Awaitable[T]]:
		"""Get the fetch function from the first observer."""
		if len(self._observers) == 0:
			raise RuntimeError(
				f"InfiniteQuery '{self.key}' has no observers. Cannot access fetch function."
			)
		return self._observers[0]._fetch_fn  # pyright: ignore[reportPrivateUsage]

	@property
	def has_interval(self) -> bool:
		return self._interval is not None

	def _select_interval_observer(
		self,
	) -> tuple[float | None, "InfiniteQueryResult[T, TParam] | None"]:
		min_interval: float | None = None
		selected: "InfiniteQueryResult[T, TParam] | None" = None

		for obs in reversed(self._observers):
			interval = obs._refetch_interval  # pyright: ignore[reportPrivateUsage]
			if interval is None:
				continue
			if not obs._enabled.value:  # pyright: ignore[reportPrivateUsage]
				continue
			if min_interval is None or interval < min_interval:
				min_interval = interval
				selected = obs

		return min_interval, selected

	def _create_interval_effect(self, interval: float) -> Effect:
		def interval_fn():
			observer = self._interval_observer
			if observer is None:
				return
			self.invalidate(fetch_fn=observer._fetch_fn, observer=observer)  # pyright: ignore[reportPrivateUsage]

		return Effect(
			interval_fn,
			name=f"inf_query_interval({self.key})",
			interval=interval,
			immediate=True,
		)

	def _update_interval(self) -> None:
		new_interval, new_observer = self._select_interval_observer()
		interval_changed = new_interval != self._interval

		self._interval = new_interval
		self._interval_observer = new_observer

		if not interval_changed:
			if self._interval_effect is None and new_interval is not None:
				self._interval_effect = self._create_interval_effect(new_interval)
			return

		if self._interval_effect is not None:
			self._interval_effect.dispose()
			self._interval_effect = None

		if new_interval is not None:
			self._interval_effect = self._create_interval_effect(new_interval)

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
	_gc_handle: TimerHandleLike | None
	_interval_effect: Effect | None
	_interval: float | None
	_interval_observer: "InfiniteQueryResult[T, TParam] | None"

	def __init__(
		self,
		key: QueryKey,
		*,
		initial_page_param: TParam,
		get_next_page_param: Callable[[list[Page[T, TParam]]], TParam | None],
		get_previous_page_param: (
			Callable[[list[Page[T, TParam]]], TParam | None] | None
		) = None,
		max_pages: int = 0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: list[Page[T, TParam]] | Missing | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.key = normalize_key(key)

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
			initial_pages = cast(list[Page[T, TParam]] | None, initial_data) or []

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
		self._interval_effect = None
		self._interval = None
		self._interval_observer = None

	# ─────────────────────────────────────────────────────────────────────────
	# Commit functions - update state after pages have been modified
	# ─────────────────────────────────────────────────────────────────────────

	async def commit(self):
		"""Commit current pages state and run success callbacks."""
		self._commit_sync()

		for obs in self._observers:
			if obs._on_success is not None:  # pyright: ignore[reportPrivateUsage]
				with Untrack():
					await maybe_await(call_flexible(obs._on_success, self.pages))  # pyright: ignore[reportPrivateUsage]

	async def _commit_error(self, error: Exception):
		"""Commit error state and run error callbacks."""
		self._commit_error_sync(error)

		for obs in self._observers:
			if obs._on_error is not None:  # pyright: ignore[reportPrivateUsage]
				with Untrack():
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

	async def wait(
		self,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
	) -> ActionResult[list[Page[T, TParam]]]:
		"""Wait for any in-flight queue processing to complete."""
		# Wait for any in-progress queue processing
		if self._queue_task and not self._queue_task.done():
			await self._queue_task
		# Return result based on current state
		if self.status() == "error":
			return ActionError(cast(Exception, self.error()))
		return ActionSuccess(list(self.pages))

	async def ensure(
		self,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
	) -> ActionResult[list[Page[T, TParam]]]:
		"""Ensure an initial fetch has started, then wait for completion."""
		if len(self.pages) == 0 and self.status() == "loading":
			if self._queue_task is None or self._queue_task.done():
				fn = fetch_fn if fetch_fn is not None else self.fn
				self._enqueue(Refetch(fetch_fn=fn, observer=observer))
		return await self.wait()

	def observe(self, observer: Any):
		self._observers.append(observer)
		self.cancel_gc()
		gc_time = getattr(observer, "_gc_time", 0)
		if gc_time and gc_time > 0:
			self.cfg.gc_time = max(self.cfg.gc_time, gc_time)
		self._update_interval()

	def unobserve(self, observer: "InfiniteQueryResult[T, TParam]"):
		"""Unregister an observer. Cancels pending actions. Schedules GC if no observers remain."""
		if observer in self._observers:
			self._observers.remove(observer)
		self._update_interval()

		# Cancel pending actions from this observer
		self._cancel_observer_actions(observer)

		if len(self._observers) == 0:
			if not self.__disposed__:
				self.schedule_gc()

	def invalidate(
		self,
		*,
		cancel_fetch: bool = False,
		refetch_page: Callable[[T, int, list[T]], bool] | None = None,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
	):
		"""Enqueue a refetch. Synchronous - does not wait for completion."""
		if cancel_fetch:
			self._cancel_queue()
		if len(self._observers) > 0:
			# Use provided fetch_fn or fall back to first observer's fetch_fn
			fn = fetch_fn if fetch_fn is not None else self.fn
			self._enqueue(
				Refetch(fetch_fn=fn, observer=observer, refetch_page=refetch_page)
			)

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
		"""Cancel all pending and in-flight actions."""
		# Cancel pending actions in the queue
		while self._queue:
			action = self._queue.popleft()
			if not action.future.done():
				action.future.cancel()

		# Cancel the currently executing action and task
		current = self.current_action.read()
		if current is not None and not current.future.done():
			current.future.cancel()

		if self._queue_task and not self._queue_task.done():
			self._queue_task.cancel()
			self._queue_task = None

	def _cancel_observer_actions(
		self, observer: "InfiniteQueryResult[T, TParam]"
	) -> None:
		"""Cancel pending actions from a specific observer.

		Note: Does not cancel the currently executing action to avoid disrupting the
		queue processor. The fetch will complete but results will be ignored since
		the observer is disposed.
		"""
		# Cancel pending actions from this observer (not the currently executing one)
		remaining: deque[Action[T, TParam]] = deque()
		while self._queue:
			action = self._queue.popleft()
			if action.observer is observer:
				if not action.future.done():
					action.future.cancel()
			else:
				remaining.append(action)
		self._queue = remaining

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
				self._queue_task = create_task(self._process_queue())
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
				# Only reset state if we're still the current action
				# (not replaced by another action via cancel_fetch)
				if self.current_action.read() is action:
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

		page = await action.fetch_fn(next_param)
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

		data = await action.fetch_fn(prev_param)
		page = Page(data, prev_param)
		self.pages.insert(0, page)
		self._trim_back()
		await self.commit()
		return page

	async def _execute_refetch_all(
		self, action: "Refetch[T, TParam]"
	) -> list[Page[T, TParam]]:
		if len(self.pages) == 0:
			page = await action.fetch_fn(self.cfg.initial_page_param)
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
				page = await action.fetch_fn(page_param)
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

		page = await action.fetch_fn(action.param)

		if action.clear or idx is None:
			# clear=True or page doesn't exist - replace all pages with just this one
			self.pages.clear()
			self.pages.append(Page(page, action.param))
		else:
			# Page exists, update it
			self.pages[idx] = Page(page, action.param)

		await self.commit()
		return page

	# ─────────────────────────────────────────────────────────────────────────
	# Public fetch API
	# ─────────────────────────────────────────────────────────────────────────

	async def fetch_next_page(
		self,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		*,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		"""
		Fetch the next page. Queued for sequential execution.

		Note: Prefer calling fetch_next_page() on InfiniteQueryResult to ensure the
		correct fetch function is used. When called directly on InfiniteQuery, uses
		the first observer's fetch function if not provided.
		"""
		fn = fetch_fn if fetch_fn is not None else self.fn
		action: FetchNext[T, TParam] = FetchNext(fetch_fn=fn, observer=observer)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def fetch_previous_page(
		self,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		*,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		"""
		Fetch the previous page. Queued for sequential execution.

		Note: Prefer calling fetch_previous_page() on InfiniteQueryResult to ensure
		the correct fetch function is used. When called directly on InfiniteQuery,
		uses the first observer's fetch function if not provided.
		"""
		fn = fetch_fn if fetch_fn is not None else self.fn
		action: FetchPrevious[T, TParam] = FetchPrevious(fetch_fn=fn, observer=observer)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def refetch(
		self,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		*,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
		cancel_fetch: bool = False,
		refetch_page: Callable[[T, int, list[T]], bool] | None = None,
	) -> ActionResult[list[Page[T, TParam]]]:
		"""
		Refetch all pages. Queued for sequential execution.

		Note: Prefer calling refetch() on InfiniteQueryResult to ensure the correct
		fetch function is used. When called directly on InfiniteQuery, uses the first
		observer's fetch function if not provided.
		"""
		fn = fetch_fn if fetch_fn is not None else self.fn
		action: Refetch[T, TParam] = Refetch(
			fetch_fn=fn, observer=observer, refetch_page=refetch_page
		)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	async def refetch_page(
		self,
		param: TParam,
		fetch_fn: Callable[[TParam], Awaitable[T]] | None = None,
		*,
		observer: "InfiniteQueryResult[T, TParam] | None" = None,
		cancel_fetch: bool = False,
		clear: bool = False,
	) -> ActionResult[T | None]:
		"""
		Refetch a page by its param. Queued for sequential execution.

		If the page doesn't exist or clear=True, clears existing pages and loads
		the requested page as the new starting point.

		Note: Prefer calling refetch_page() on InfiniteQueryResult to ensure the
		correct fetch function is used. When called directly on InfiniteQuery, uses
		the first observer's fetch function if not provided.
		"""
		fn = fetch_fn if fetch_fn is not None else self.fn
		action: RefetchPage[T, TParam] = RefetchPage(
			fetch_fn=fn, param=param, observer=observer, clear=clear
		)
		return await self._enqueue(action, cancel_fetch=cancel_fetch)

	@override
	def dispose(self):
		self.cancel_gc()
		self._cancel_queue()
		if self._queue_task and not self._queue_task.done():
			self._queue_task.cancel()
		if self._interval_effect is not None:
			self._interval_effect.dispose()
			self._interval_effect = None
		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)


def none_if_missing(value: Any):
	return None if value is MISSING else value


class InfiniteQueryResult(Generic[T, TParam], Disposable):
	"""Observer wrapper for InfiniteQuery with lifecycle and stale tracking.

	InfiniteQueryResult provides the interface for interacting with paginated
	queries. It manages observation lifecycle, staleness tracking, and exposes
	reactive properties and methods for pagination.

	Attributes:
		data: List of Page objects or None if not loaded.
		pages: List of page data only (without params) or None.
		page_params: List of page parameters only or None.
		error: The last error encountered, or None.
		status: Current QueryStatus ("loading", "success", "error").
		is_loading: Whether status is "loading".
		is_success: Whether status is "success".
		is_error: Whether status is "error".
		is_fetching: Whether any fetch is in progress.
		has_next_page: Whether more pages are available forward.
		has_previous_page: Whether previous pages are available.
		is_fetching_next_page: Whether fetching the next page.
		is_fetching_previous_page: Whether fetching the previous page.

	Example:

	```python
	# Access infinite query result
	if state.posts.is_loading:
	    show_skeleton()
	elif state.posts.data:
	    for page in state.posts.data:
	        render_posts(page.data)
	    if state.posts.has_next_page:
	        Button("Load More", on_click=state.posts.fetch_next_page)
	```
	"""

	_query: Computed[InfiniteQuery[T, TParam]]
	_fetch_fn: Callable[[TParam], Awaitable[T]]
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_keep_previous_data: bool
	_on_success: Callable[[list[Page[T, TParam]]], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_observe_effect: Effect
	_data_computed: Computed[list[Page[T, TParam]] | None | Missing]
	_enabled: Signal[bool]
	_fetch_on_mount: bool

	def __init__(
		self,
		query: Computed[InfiniteQuery[T, TParam]],
		fetch_fn: Callable[[TParam], Awaitable[T]],
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
		self._fetch_fn = fetch_fn
		self._stale_time = stale_time
		self._gc_time = gc_time
		interval = (
			refetch_interval
			if refetch_interval is not None and refetch_interval > 0
			else None
		)
		self._refetch_interval = interval
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

				# Skip if query interval is active - interval effect handles initial fetch
				if enabled and fetch_on_mount and not q.has_interval:
					# Fetch if no data loaded yet or if existing data is stale
					if not q.is_fetching() and (
						q.status() == "loading" or self.is_stale()
					):
						q.invalidate()

			# Return cleanup function that captures the query (old query on key change)
			def cleanup():
				q.unobserve(self)

			return cleanup

		self._observe_effect = Effect(
			observe_effect,
			name=f"inf_query_observe({self._query().key})",
			immediate=True,
		)
		self._data_computed = Computed(
			self._data_computed_fn,
			name=f"inf_query_data({self._query().key})",
			initial_value=MISSING,
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
		self, prev: list[Page[T, TParam]] | None | Missing
	) -> list[Page[T, TParam]] | None | Missing:
		query = self._query()
		if self._keep_previous_data and query.status() == "loading":
			return prev
		# Access pages.version to subscribe to structural changes
		if len(query.pages) == 0:
			return MISSING
		return unwrap(query.pages)

	@property
	def data(self) -> list[Page[T, TParam]] | None:
		return none_if_missing(self._data_computed())

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
		query = self._query()
		return (time.time() - query.last_updated.read()) > self._stale_time

	async def fetch_next_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		return await self._query().fetch_next_page(
			self._fetch_fn, observer=self, cancel_fetch=cancel_fetch
		)

	async def fetch_previous_page(
		self,
		*,
		cancel_fetch: bool = False,
	) -> ActionResult[Page[T, TParam] | None]:
		return await self._query().fetch_previous_page(
			self._fetch_fn, observer=self, cancel_fetch=cancel_fetch
		)

	async def fetch_page(
		self,
		page_param: TParam,
		*,
		cancel_fetch: bool = False,
		clear: bool = False,
	) -> ActionResult[T | None]:
		"""Fetch a specific page by its param.

		Args:
			page_param: The page parameter to fetch.
			cancel_fetch: Cancel any in-flight fetches before starting.
			clear: If True, clears all other pages and keeps only the fetched page.
				Useful for resetting pagination to a specific page.
		"""
		return await self._query().refetch_page(
			page_param,
			fetch_fn=self._fetch_fn,
			observer=self,
			cancel_fetch=cancel_fetch,
			clear=clear,
		)

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
			self._fetch_fn,
			observer=self,
			cancel_fetch=cancel_fetch,
			refetch_page=refetch_page,
		)

	async def wait(self) -> ActionResult[list[Page[T, TParam]]]:
		return await self._query().wait(fetch_fn=self._fetch_fn, observer=self)

	async def ensure(self) -> ActionResult[list[Page[T, TParam]]]:
		return await self._query().ensure(fetch_fn=self._fetch_fn, observer=self)

	def invalidate(self):
		query = self._query()
		query.invalidate(fetch_fn=self._fetch_fn, observer=self)

	def enable(self):
		self._enabled.write(True)
		self._query()._update_interval()  # pyright: ignore[reportPrivateUsage]

	def disable(self):
		self._enabled.write(False)
		self._query()._update_interval()  # pyright: ignore[reportPrivateUsage]

	def set_error(self, error: Exception):
		query = self._query()
		query.set_error(error)

	@override
	def dispose(self):
		"""Clean up the result and its observe effect."""
		self._observe_effect.dispose()


class InfiniteQueryProperty(Generic[T, TParam, TState], InitializableProperty):
	"""Descriptor for state-bound infinite queries created by the @infinite_query decorator.

	InfiniteQueryProperty is the return type of the ``@infinite_query`` decorator.
	It acts as a descriptor that creates and manages InfiniteQueryResult instances
	for each State object.

	When accessed on a State instance, returns an InfiniteQueryResult with reactive
	properties for pagination state and methods for fetching pages.

	Required decorators:
		- ``@infinite_query_prop.key``: Define the query key (required).
		- ``@infinite_query_prop.get_next_page_param``: Define how to get next page param.

	Optional decorators:
		- ``@infinite_query_prop.get_previous_page_param``: For bi-directional pagination.
		- ``@infinite_query_prop.initial_data``: Provide initial pages.
		- ``@infinite_query_prop.on_success``: Handle successful fetch.
		- ``@infinite_query_prop.on_error``: Handle fetch errors.

	Example:

	```python
	class FeedState(ps.State):
	    feed_type: str = "home"

	    @ps.infinite_query(initial_page_param=None)
	    async def posts(self, cursor: str | None) -> list[Post]:
	        return await api.get_posts(cursor=cursor)

	    @posts.key
	    def _posts_key(self):
	        return ("feed", self.feed_type)

	    @posts.get_next_page_param
	    def _next_cursor(self, pages: list[Page]) -> str | None:
	        if not pages:
	            return None
	        last = pages[-1]
	        return last.data[-1].id if last.data else None
	```
	"""

	name: str
	_fetch_fn: "Callable[[TState, TParam], Awaitable[T]]"
	_keep_alive: bool
	_keep_previous_data: bool
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_retries: int
	_retry_delay: float
	_initial_data: (
		list[Page[T, TParam]]
		| Callable[[TState], list[Page[T, TParam]]]
		| Missing
		| None
	)
	_initial_page_param: TParam
	_get_next_page_param: (
		Callable[[TState, list[Page[T, TParam]]], TParam | None] | None
	)
	_get_previous_page_param: (
		Callable[[TState, list[Page[T, TParam]]], TParam | None] | None
	)
	_max_pages: int
	_key: Key | Callable[[TState], Key] | None
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
		self._initial_data = MISSING
		if key is None:
			self._key = None
		elif callable(key):
			key_fn = key

			def normalized_key(state: TState) -> Key:
				return normalize_key(key_fn(state))

			self._key = normalized_key
		else:
			self._key = normalize_key(key)
		self._initial_data_updated_at = initial_data_updated_at
		self._enabled = enabled
		self._fetch_on_mount = fetch_on_mount
		self._priv_result = f"__inf_query_{name}"

	def key(self, fn: Callable[[TState], QueryKey]):
		if self._key is not None:
			raise RuntimeError(
				f"Cannot use @{self.name}.key decorator when a key is already provided to @infinite_query(key=...)."
			)

		def normalized_key(state: TState) -> Key:
			return normalize_key(fn(state))

		self._key = normalized_key
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

	def initial_data(
		self, fn: Callable[[TState], list[Page[T, TParam]]]
	) -> Callable[[TState], list[Page[T, TParam]]]:
		if self._initial_data is not MISSING:
			raise RuntimeError(
				f"Duplicate initial_data() decorator for infinite query '{self.name}'. Only one is allowed."
			)
		self._initial_data = fn
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
			# pyright: ignore[reportImplicitStringConcatenation]
			raise RuntimeError(
				f"Missing query key for @infinite_query '{self.name}'. "
				+ "A key is required to cache and share query results.\n\n"
				+ f"Fix: Add key=(...) to the decorator or use the @{self.name}.key decorator:\n\n"
				+ "    @ps.infinite_query(initial_page_param=..., key=('my_query',))\n"
				+ f"    async def {self.name}(self, param): ...\n\n"
				+ "Or with a dynamic key:\n\n"
				+ f"    @{self.name}.key\n"
				+ f"    def _{self.name}_key(self):\n"
				+ "        return ('my_query', self.some_param)"
			)
		raw_initial = (
			call_flexible(self._initial_data, state)
			if callable(self._initial_data)
			else self._initial_data
		)
		initial_data = (
			MISSING
			if raw_initial is MISSING
			else cast(list[Page[T, TParam]] | None, raw_initial)
		)
		query = self._resolve_keyed(
			state,
			fetch_fn,
			next_fn,
			prev_fn,
			initial_data,
			self._initial_data_updated_at,
		)

		on_success = None
		if self._on_success_fn:
			bound_fn = bind_state(state, self._on_success_fn)

			async def on_success_wrapper(data: list[Page[T, TParam]]):
				await maybe_await(call_flexible(bound_fn, [p.data for p in data]))

			on_success = on_success_wrapper

		result = InfiniteQueryResult(
			query=query,
			fetch_fn=fetch_fn,
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
		initial_data: list[Page[T, TParam]] | Missing | None,
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
					initial_page_param=self._initial_page_param,
					get_next_page_param=next_fn,
					get_previous_page_param=prev_fn,
					max_pages=self._max_pages,
					initial_data=initial_data,
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
	key: QueryKey | Callable[[TState], QueryKey] | None = None,
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
) -> InfiniteQueryProperty[T, TParam, TState]: ...


@overload
def infinite_query(
	fn: None = None,
	*,
	key: QueryKey | Callable[[TState], QueryKey] | None = None,
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
) -> Callable[
	[Callable[[TState, Any], Awaitable[T]]],
	InfiniteQueryProperty[T, TParam, TState],
]: ...


def infinite_query(
	fn: Callable[[TState, TParam], Awaitable[T]] | None = None,
	*,
	key: QueryKey | Callable[[TState], QueryKey] | None = None,
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
) -> (
	InfiniteQueryProperty[T, TParam, TState]
	| Callable[
		[Callable[[TState, Any], Awaitable[T]]],
		InfiniteQueryProperty[T, TParam, TState],
	]
):
	"""Decorator for paginated queries on State methods.

	Creates a reactive infinite query that supports cursor-based or offset-based
	pagination. Data is stored as a list of pages, each with its data and the
	parameter used to fetch it.

	Requires a key (``key=`` or ``@query_prop.key``) and
	``@query_prop.get_next_page_param`` decorator.

	Args:
		fn: The async method to decorate (when used without parentheses).
		initial_page_param: The parameter for fetching the first page (required).
		max_pages: Maximum pages to keep in memory (0 = unlimited).
		stale_time: Seconds before data is considered stale (default 0.0).
		gc_time: Seconds to keep unused query in cache (default 300.0).
		refetch_interval: Auto-refetch interval in seconds (default None).
		keep_previous_data: Keep previous data while loading (default False).
		retries: Number of retry attempts on failure (default 3).
		retry_delay: Delay between retries in seconds (default 2.0).
		initial_data_updated_at: Timestamp for initial data staleness.
		enabled: Whether query is enabled (default True).
		fetch_on_mount: Fetch when component mounts (default True).
		key: Static query key for sharing across instances.

	Returns:
		InfiniteQueryProperty that creates InfiniteQueryResult instances when accessed.

	Example:

	```python
	class FeedState(ps.State):
	    @ps.infinite_query(initial_page_param=None, key=("feed",))
	    async def posts(self, cursor: str | None) -> list[Post]:
	        return await api.get_posts(cursor=cursor)

	    @posts.key
	    def _posts_key(self):
	        return ("feed", self.feed_type)

	    @posts.get_next_page_param
	    def _next_cursor(self, pages: list[Page]) -> str | None:
	        if not pages:
	            return None
	        last = pages[-1]
	        return last.data[-1].id if last.data else None

	    @posts.get_previous_page_param
	    def _prev_cursor(self, pages: list[Page]) -> str | None:
	        if not pages:
	            return None
	        first = pages[0]
	        return first.data[0].id if first.data else None
	```
	"""

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
