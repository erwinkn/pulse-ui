import asyncio
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


@ps.component
def InfiniteQueryDemo():
	state = ps.states(Feed)
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
	)


app = ps.App([ps.Route("/", InfiniteQueryDemo)])
