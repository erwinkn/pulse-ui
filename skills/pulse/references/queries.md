# Queries & Mutations

Async data fetching with caching, loading states, and automatic refetching.

## `@ps.query`

Cached async data fetching on State methods.

```python
class UserState(ps.State):
    user_id: int = 1

    @ps.query
    async def user(self) -> dict:
        return await api.get_user(self.user_id)
```

### Query Options

```python
@ps.query(
    stale_time=0,            # Seconds before data considered stale (default 0)
    gc_time=300.0,           # Seconds before unused cache is garbage collected
    retries=3,               # Retry attempts on failure
    retry_delay=2.0,         # Delay between retries in seconds
    keep_previous_data=True, # Keep old data while refetching
    enabled=True,            # Whether query runs automatically (default True)
    fetch_on_mount=True,     # Fetch when component mounts (default True)
    refetch_interval=None,   # Auto-refetch interval in seconds (None = disabled)
)
async def data(self) -> T: ...
```

### Cache Key

Define explicit cache key for deduplication across components:

```python
@ps.query
async def user(self) -> dict:
    return await api.get_user(self.user_id)

@user.key
def _user_key(self):
    return ("user", self.user_id)  # Tuple key
```

Without explicit key, query uses auto-tracking (re-runs when any read signal changes).

### Initial Data

Provide initial/cached data before first fetch:

```python
@ps.query
async def user(self) -> dict:
    return await api.get_user(self.user_id)

@user.initial_data
def _initial(self) -> dict:
    return {"id": 0, "name": "Loading..."}
```

### Callbacks

```python
@ps.query
async def data(self) -> T: ...

@data.on_success
def _success(self):
    print("Fetch succeeded")

@data.on_error
def _error(self):
    print("Fetch failed")
```

### Enabled & Fetch Control

Control when queries run:

```python
@ps.query(enabled=False)  # Query won't run automatically
async def data(self) -> T: ...

@ps.query(fetch_on_mount=False)  # Don't fetch when component mounts
async def lazy_data(self) -> T: ...

@ps.query(refetch_interval=5.0)  # Refetch every 5 seconds
async def live_data(self) -> T: ...
```

Enable/disable programmatically:

```python
state.data.enable()   # Enable the query
state.data.disable()  # Disable the query
```

### Query Properties

Access in components:

```python
state.user.data         # T | None — fetched data
state.user.error        # Exception | None — last error
state.user.status       # "loading" | "success" | "error"
state.user.is_loading   # True if loading (no data yet)
state.user.is_fetching  # True if fetch in progress (including refetch)
state.user.is_success   # True if last fetch succeeded
state.user.is_error     # True if last fetch failed
state.user.is_scheduled # True if a refetch is scheduled/running
```

### Query Methods

```python
state.user.refetch()     # Force refetch
state.user.invalidate()  # Mark stale, refetch if observed
state.user.set_data(val) # Manually set data (optimistic update)
await state.user.wait()  # Wait for current fetch to complete
state.user.enable()      # Enable the query
state.user.disable()     # Disable the query
```

### Usage Pattern

```python
@ps.component
def UserProfile():
    with ps.init():
        state = UserState()

    if state.user.is_loading:
        return ps.div("Loading...")

    if state.user.is_error:
        return ps.div(f"Error: {state.user.error}")

    user = state.user.data
    return ps.div(
        ps.h1(user["name"]),
        ps.button("Refresh", onClick=lambda: state.user.refetch()),
    )
```

## `@ps.mutation`

Non-cached operations (create, update, delete). No auto-caching.

```python
class UserState(ps.State):
    user_id: int = 1

    @ps.query
    async def user(self) -> dict:
        return await api.get_user(self.user_id)

    @ps.mutation
    async def update_name(self, name: str) -> dict:
        result = await api.update_user(self.user_id, {"name": name})
        self.user.invalidate()  # Refresh related query
        return result

    @ps.mutation
    async def delete_user(self) -> None:
        await api.delete_user(self.user_id)
```

### Mutation Callbacks

```python
@ps.mutation
async def update_name(self, name: str) -> dict: ...

@update_name.on_success
def _success(self, result: dict):
    print(f"Updated: {result}")

@update_name.on_error
def _error(self, error: Exception):
    print(f"Failed: {error}")
```

### Calling Mutations

```python
# Fire and forget
ps.button("Save", onClick=lambda: state.update_name("New Name"))

# With await
async def handle_save():
    try:
        result = await state.update_name("New Name")
        print(f"Saved: {result}")
    except Exception as e:
        print(f"Error: {e}")

ps.button("Save", onClick=handle_save)
```

## `@ps.infinite_query`

Pagination with automatic page merging. **Always requires a key** (via `key=` param or `@query.key` decorator).

Why require keys? Unlike regular queries, infinite queries accumulate pages. Auto-dependency tracking would reset all pages on any dependency change, causing confusing UX where scroll position and content disappear unexpectedly.

```python
class FeedState(ps.State):
    @ps.infinite_query(initial_page_param=None, key=("posts",))  # static key
    async def posts(self, page_param: str | None) -> dict:
        return await api.get_posts(cursor=page_param, limit=20)

    @posts.get_next_page_param
    def _next(self, pages: list) -> str | None:
        if not pages:
            return None
        return pages[-1].data.get("next_cursor")  # None = no more pages
```

For dynamic keys:

```python
class FeedState(ps.State):
    feed_type: str = "recent"

    @ps.infinite_query(initial_page_param=None)
    async def posts(self, cursor: str | None) -> dict:
        return await api.get_posts(feed_type=self.feed_type, cursor=cursor)

    @posts.key
    def _key(self):
        return ("posts", self.feed_type)  # pages reset when feed_type changes

    @posts.get_next_page_param
    def _next(self, pages: list) -> str | None:
        return pages[-1].data.get("next_cursor") if pages else None
```

### Infinite Query Options

```python
@ps.infinite_query(
    initial_page_param=None,  # Parameter for first page (required)
    key=("feed",),            # Query key (required, or use @query.key)
    max_pages=0,              # Max pages to keep in memory (0 = unlimited)
    stale_time=0,             # Seconds before data considered stale
    gc_time=300.0,            # Seconds before unused cache is garbage collected
    refetch_interval=None,    # Auto-refetch interval in seconds
    keep_previous_data=False, # Keep old data while refetching
    retries=3,                # Retry attempts on failure
    retry_delay=2.0,          # Delay between retries in seconds
    enabled=True,             # Whether query runs automatically
    fetch_on_mount=True,      # Fetch when component mounts
)
async def feed(self, page_param: int) -> list: ...
```

### Bidirectional Pagination

```python
@ps.infinite_query(initial_page_param=None, key=("posts",))
async def posts(self, cursor: str | None) -> dict:
    return await api.get_posts(cursor=cursor)

@posts.get_next_page_param
def _next(self, pages: list) -> str | None:
    if not pages:
        return None
    return pages[-1].data.get("next_cursor")

@posts.get_previous_page_param
def _prev(self, pages: list) -> str | None:
    if not pages:
        return None
    return pages[0].data.get("prev_cursor")
```

### Infinite Query Properties

```python
state.posts.data                    # list[Page] — all pages with data and params
state.posts.pages                   # list[T] — individual page results (data only)
state.posts.page_params             # list[TParam] — page parameters only
state.posts.has_next_page           # True if more pages available forward
state.posts.has_previous_page       # True if previous pages available
state.posts.is_fetching_next_page   # True if loading next page
state.posts.is_fetching_previous_page  # True if loading previous page
state.posts.is_fetching             # True if any fetch in progress
state.posts.is_loading              # True if loading (no data yet)
state.posts.is_success              # True if last fetch succeeded
state.posts.is_error                # True if last fetch failed
```

### Infinite Query Methods

```python
await state.posts.fetch_next_page()      # Load next page
await state.posts.fetch_previous_page()  # Load previous page (bidirectional)
await state.posts.fetch_page(param)      # Refetch specific page by param
await state.posts.fetch_page(param, clear=True)  # Refetch page and clear all others
await state.posts.refetch()              # Refetch all pages
await state.posts.wait()                 # Wait for current fetch to complete
state.posts.invalidate()                 # Mark stale, trigger refetch
state.posts.set_data(pages)              # Manually set pages
state.posts.enable()                     # Enable the query
state.posts.disable()                    # Disable the query
```

### Selective Page Refetch

Refetch only specific pages using a filter function:

```python
# Only refetch first page
await state.posts.refetch(
    refetch_page=lambda data, index, all_pages: index == 0
)
```

### Usage Pattern

```python
@ps.component
def InfiniteFeed():
    with ps.init():
        state = FeedState()

    if state.posts.is_loading:
        return ps.div("Loading...")

    return ps.div(
        ps.ul(
            ps.For(
                state.posts.pages or [],  # Use .pages for data only
                lambda posts, _: ps.For(
                    posts,
                    lambda post, _: ps.li(post["title"], key=str(post["id"])),
                ),
            )
        ),
        state.posts.has_next_page and ps.button(
            "Load More" if not state.posts.is_fetching_next_page else "Loading...",
            onClick=lambda: state.posts.fetch_next_page(),
            disabled=state.posts.is_fetching_next_page,
        ),
    )
```

### Infinite Query Callbacks

```python
@ps.infinite_query(initial_page_param=0, key=("feed",))
async def feed(self, page: int) -> list: ...

@feed.get_next_page_param
def _next(self, pages: list) -> int | None:
    return len(pages) if pages else None

@feed.on_success
def _success(self, pages: list):
    print(f"Loaded {len(pages)} pages")

@feed.on_error
def _error(self, error: Exception):
    print(f"Failed: {error}")
```

## QueryClient

Session-level query cache management.

```python
client = ps.queries

# Invalidate by key
client.invalidate(("user", 1))  # Exact match
client.invalidate_prefix(("user",))  # Prefix match

# Get cached data
data = client.get_data(("user", 1))

# Set cached data
client.set_data(("user", 1), {"id": 1, "name": "Updated"})

# Filter multiple keys
client.invalidate(ps.keys(("user", 1), ("user", 2)))
```

## Optimistic Updates

Update UI before server confirms:

```python
class TodoState(ps.State):
    @ps.query
    async def todos(self) -> list[dict]: ...

    @ps.mutation
    async def add_todo(self, text: str) -> dict:
        # Optimistic update
        current = self.todos.data or []
        optimistic = {"id": "temp", "text": text, "done": False}
        self.todos.set_data([*current, optimistic])

        # Server call
        result = await api.create_todo(text)

        # Refresh with real data
        self.todos.invalidate()
        return result
```

## Error Handling

```python
class DataState(ps.State):
    @ps.query(retries=3, retry_delay=2.0)
    async def data(self) -> dict:
        response = await api.fetch()
        if not response.ok:
            raise ValueError(f"API error: {response.status}")
        return response.json()

@ps.component
def DataView():
    with ps.init():
        state = DataState()

    if state.data.is_error:
        return ps.div(
            ps.p(f"Error: {state.data.error}"),
            ps.button("Retry", onClick=lambda: state.data.refetch()),
        )

    return ps.div(str(state.data.data))
```

## Query Dependencies

Queries that depend on other queries:

```python
class ChainedState(ps.State):
    @ps.query
    async def user(self) -> dict:
        return await api.get_user()

    @ps.query
    async def posts(self) -> list[dict]:
        # Wait for user to load first
        user = await self.user.wait()
        return await api.get_posts(user["id"])

    @posts.key
    def _posts_key(self):
        # Key includes user to refetch when user changes
        user = self.user.data
        return ("posts", user["id"] if user else None)
```

## See Also

- `reactive.md` - Effect for polling patterns
- `middleware.md` - Session management and QueryClient scope
- `state.md` - State class with @ps.query
