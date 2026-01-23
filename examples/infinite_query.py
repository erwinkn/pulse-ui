import asyncio
import time
from typing import TypedDict

import pulse as ps
from pulse.queries.infinite_query import Page


class Item(TypedDict):
	id: str
	text: str


class PageData(TypedDict):
	page: int
	items: list[Item]
	next: int | None
	prev: int | None


class IntervalPage(TypedDict):
	source: str
	calls: int
	updated_at: float


class Feed(ps.State):
	"""Demonstrates all infinite query features."""

	page_size: int = 3
	max_page: int = 12

	@ps.infinite_query(
		initial_page_param=0,
		max_pages=4,
		retries=1,
	)
	async def feed_page(self, page_param: int):
		# Simulate network latency
		await asyncio.sleep(0.15)

		# Fake API payload with cursors in the page data itself
		next_param = page_param + 1 if page_param < self.max_page else None
		prev_param = page_param - 1 if page_param > 0 else None
		items: list[Item] = [
			{
				"id": f"{page_param}-{i}",
				"text": f"Item {page_param}:{i}",
			}
			for i in range(self.page_size)
		]
		return PageData(
			page=page_param,
			items=items,
			next=next_param,
			prev=prev_param,
		)

	@feed_page.get_next_page_param
	def _get_next_page_param(self, pages: list[Page[PageData, int]]) -> int | None:
		return pages[-1].data["next"] if pages else None

	@feed_page.get_previous_page_param
	def _get_previous_page_param(self, pages: list[Page[PageData, int]]) -> int | None:
		return pages[0].data["prev"] if pages else None

	@feed_page.key
	def _key(self):
		# Keyed so changing page_size resets the feed instance
		return ("feed", self.page_size)


class IntervalFastState(ps.State):
	calls: int = 0

	@ps.infinite_query(initial_page_param=0, retries=0, refetch_interval=0.5)
	async def interval(self, page_param: int) -> IntervalPage:
		self.calls += 1
		await asyncio.sleep(0)
		return {
			"source": "fast",
			"calls": self.calls,
			"updated_at": time.time(),
		}

	@interval.get_next_page_param
	def _fast_next(self, pages: list[Page[IntervalPage, int]]) -> int | None:
		return None

	@interval.key
	def _fast_key(self):
		return ("interval-feed",)


class IntervalSlowState(ps.State):
	calls: int = 0

	@ps.infinite_query(initial_page_param=0, retries=0, refetch_interval=1.5)
	async def interval(self, page_param: int) -> IntervalPage:
		self.calls += 1
		await asyncio.sleep(0)
		return {
			"source": "slow",
			"calls": self.calls,
			"updated_at": time.time(),
		}

	@interval.get_next_page_param
	def _slow_next(self, pages: list[Page[IntervalPage, int]]) -> int | None:
		return None

	@interval.key
	def _slow_key(self):
		return ("interval-feed",)


class IntervalToggleState(ps.State):
	show_fast: bool = True
	show_slow: bool = True


@ps.component
def IntervalObserver(label: str, state_cls: type[ps.State], enabled: bool):
	with ps.init():
		s = state_cls()

	if enabled:
		s.interval.enable()
	else:
		s.interval.disable()

	pages = s.interval.pages or []
	page = pages[0] if pages else None
	if not enabled and page is None:
		page_label = "Disabled"
	else:
		page_label = "Loading..." if page is None else f"{page}"
	status = "enabled" if enabled else "disabled"

	return ps.div(
		ps.p(
			f"{label} ({status}) calls={s.calls}",
			className="text-xs text-gray-600",
		),
		ps.p(
			f"{label} data={page_label}",
			className="text-xs text-gray-600",
		),
	)


@ps.component
def InfiniteQueryDemo():
	with ps.init():
		state = Feed()
		interval_toggle = IntervalToggleState()
	query = state.feed_page

	async def load_next():
		await query.fetch_next_page()

	async def load_prev():
		await query.fetch_previous_page()

	async def jump_to_first():
		await query.fetch_page(0)

	async def jump_to_last():
		await query.fetch_page(state.max_page)

	async def refetch_all():
		await query.refetch()

	def set_small_page():
		state.page_size = 2

	def set_big_page():
		state.page_size = 5

	def toggle_fast():
		interval_toggle.show_fast = not interval_toggle.show_fast

	def toggle_slow():
		interval_toggle.show_slow = not interval_toggle.show_slow

	pages = query.pages or []
	flattened = [item for page in pages for item in page["items"]]

	return ps.div(
		ps.h2("Infinite Query Demo", className="text-xl font-semibold mb-2"),
		ps.div(
			ps.button(
				"Prev page",
				disabled=not query.has_previous_page or query.is_fetching_previous_page,
				onClick=load_prev,
				className="btn-secondary mr-2",
			),
			ps.button(
				"Next page",
				disabled=not query.has_next_page or query.is_fetching_next_page,
				onClick=load_next,
				className="btn-primary mr-2",
			),
			ps.button(
				"Jump to first", onClick=jump_to_first, className="btn-secondary mr-2"
			),
			ps.button(
				"Jump to last", onClick=jump_to_last, className="btn-secondary mr-2"
			),
			ps.button(
				"Refetch visible window",
				onClick=refetch_all,
				className="btn-secondary mr-2",
			),
			ps.button(
				"Set page size = 2",
				onClick=set_small_page,
				className="btn-secondary mr-2",
			),
			ps.button(
				"Set page size = 5", onClick=set_big_page, className="btn-secondary"
			),
			className="mb-3 flex flex-wrap gap-2",
		),
		ps.div(
			f"has_next_page={query.has_next_page}, has_previous_page={query.has_previous_page}, "
			+ f"is_fetching_next_page={query.is_fetching_next_page}, "
			+ f"is_fetching_previous_page={query.is_fetching_previous_page}",
			className="text-sm text-gray-600 mb-2",
		),
		ps.div(
			f"visible pages: {[p['page'] for p in pages]} (max_pages=4 trims older pages)",
			className="text-sm text-gray-600 mb-2",
		),
		ps.ul(
			*(ps.li(item["text"], key=item["id"]) for item in flattened),
			className="list-disc pl-5",
		),
		ps.div(
			ps.h3(
				"Interval Observers (min interval wins)",
				className="text-lg font-semibold mb-2",
			),
			ps.p(
				"Two observers share the same infinite query key with different intervals.",
				className="text-xs text-gray-600 mb-2",
			),
			ps.div(
				ps.button(
					"Disable fast (0.5s)"
					if interval_toggle.show_fast
					else "Enable fast (0.5s)",
					onClick=toggle_fast,
					className="btn-secondary mr-2",
				),
				ps.button(
					"Disable slow (1.5s)"
					if interval_toggle.show_slow
					else "Enable slow (1.5s)",
					onClick=toggle_slow,
					className="btn-secondary",
				),
				className="mb-3 flex flex-wrap gap-2",
			),
			ps.p(
				"Observer data is shared; call counters show which observer drives refetches.",
				className="text-xs text-gray-600 mb-2",
			),
			ps.div(
				IntervalObserver("fast", IntervalFastState, interval_toggle.show_fast),
				IntervalObserver("slow", IntervalSlowState, interval_toggle.show_slow),
				className="space-y-2",
			),
			className="mt-6 p-3 rounded bg-white shadow",
		),
	)


app = ps.App([ps.Route("/", InfiniteQueryDemo)])
