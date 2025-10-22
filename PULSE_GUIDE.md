# Pulse Coding Guide

## Core Principles
- Keep renders deterministic by deriving the UI from inputs and state only.
  ```python
  import pulse as ps

  @ps.component
  def Greeting(name: str):
      return ps.h1(f"Hello {name}!")
  ```

## Components
- Always wrap UI functions with `@ps.component` and return a plain element tree.
  ```python
  @ps.component
  def Hero():
      return ps.div(className="stack")[
          ps.h1("Pulse FTW"),
          ps.p("Ship quickly with simple Python."),
      ]
  ```

- Keep props close to their elements and compose small components.
  ```python
  @ps.component
  def Card(title: str, body: str):
      return ps.section(className="card")[
          ps.h2(title, className="card-title"),
          ps.p(body, className="card-body"),
      ]
  ```

## State
- Model interactive data with `ps.State` classes and type-annotated fields.
  ```python
  class Counter(ps.State):
      count: int = 0

      def increment(self):
          self.count += 1
  ```

- Retrieve state via `ps.states`, passing callables that build each state exactly once (state classes are callables too, but `lambda: MyState()` keeps heavier setup lazy).
  ```python
  @ps.component
  def CounterView():
      counter = ps.states(lambda: Counter())
      return ps.button(f"Count: {counter.count}", onClick=counter.increment)
  ```

## Hooks
- Call each hook only once per component render. `ps.setup` runs a synchronous initializer during the first render, caches its return value, and hands it back on later renders. Perfect for mount-only configuration or wiring helper objects.
  ```python
  from datetime import datetime
  import pulse as ps

  @ps.component
  def SessionBanner(user_id: int):
      meta = ps.setup(lambda: {"started_at": datetime.utcnow()})
      counter = ps.states(lambda: Counter())

      def announce():
          print(f"User {user_id} mounted at {meta['started_at']}")
          return lambda: print(f"User {user_id} left")

      ps.effects(announce, key=str(user_id))
      return ps.div(
          ps.p(f"Started at {meta['started_at']:%H:%M:%S}"),
          ps.button("Increment", onClick=counter.increment),
      )
  ```

- `ps.effects` registers one or more effect functions that run immediately after the initial render (and whenever their `key` changes). Each function may return a cleanup, and you can provide `on_error=` to centralize error handling.

- Use the `key` argument when hook inputs should trigger a reset.
  ```python
  import pulse as ps

  class Greeting(ps.State):
      name: str

      def __init__(self, name: str):
          self.name = name

  @ps.component
  def UserPanel(user_id: int):
      greeting = ps.states(lambda: Greeting(name=f"User {user_id}"), key=str(user_id))
      return ps.span(greeting.name)
  ```

- Stabilize changing callables or values with `ps.stable`.
  ```python
  @ps.component
  def SearchBox(on_submit):
      submit = ps.stable("submit", on_submit)
      return ps.form(onSubmit=lambda event: submit()(event["target"]["value"]))
  ```

## Derived Data
- Use `@ps.computed` for cached projections of reactive fields.
  ```python
  class TodoList(ps.State):
      items: list[str] = []
      filter: str = "all"

      @ps.computed
      def visible(self) -> list[str]:
          return [item for item in self.items if self.filter == "all" or item.startswith(self.filter)]
  ```

## Effects & Async
- Encapsulate side effects in `@ps.effect` methods and return cleanups when needed.
  ```python
  class Tracker(ps.State):
      value: int = 0

      @ps.effect
      def log(self):
          print(f"value={self.value}")
          return lambda: print("cleanup")
  ```

- Write async state methods freely; Pulse batches their updates.
  ```python
  import asyncio

  class Loader(ps.State):
      status: str = "idle"

      async def fetch(self):
          self.status = "loading"
          await asyncio.sleep(0.1)
          self.status = "done"
  ```

## Queries
- Decorate async state methods with `@ps.query`. Queries auto-track every reactive attribute you read, so referencing `self.user_id` is enough to refetch whenever that value changes.
- Add a `@query.key` when you need explicit control over reruns. Keys are ideal for batching composite dependencies and (soon) will unlock cross-component caching for identical keys.
- Each query instance exposes `.data`, `.error`, `.is_loading`, `.is_error`, `.has_loaded`, and `.refetch()`. You can update state eagerly with `.set_data()` or seed values before the first load via `.set_initial_data()`.
- Customize lifecycle hooks using decorators: `@query.initial_data` for synchronous fallbacks, `@query.on_success` for happy-path side effects, and `@query.on_error` for error reporting.
  ```python
  import pulse as ps
  import asyncio

  async def fetch_profile(user_id: int) -> dict[str, str]:
      await asyncio.sleep(0.1)
      return {"id": user_id, "name": f"User {user_id}"}

  class UserState(ps.State):
      user_id: int = 1

      @ps.query(keep_previous_data=True)
      async def profile(self) -> dict[str, str]:
          return await fetch_profile(self.user_id)

      @profile.key
      def _profile_key(self):
          return ("profile", self.user_id)

      @profile.initial_data
      def _initial_profile(self):
          return {"id": self.user_id, "name": "Loading..."}

      @profile.on_success
      def _profile_loaded(self, data: dict[str, str]):
          print(f"Loaded {data['name']}")

      @profile.on_error
      def _profile_failed(self, error: Exception):
          print(f"Failed to load user: {error}")

  @ps.component
  def ProfileCard():
      state = ps.states(lambda: UserState())
      query = state.profile
      if query.is_loading and not query.has_loaded:
          return ps.span("Fetching profile...")
      if query.is_error:
          return ps.span(f"Error: {query.error}")
      return ps.div(
          ps.h2(query.data["name"]),
          ps.button("Refresh", onClick=query.refetch),
      )
  ```

## Collections & Keys
- Prefer `ps.For` or helper functions when rendering lists, and supply stable keys.
  ```python
  @ps.component
  def TodoItems(items: list[dict]):
      return ps.ul(
          ps.For(
              items,
              lambda item: ps.li(item["title"], key=item["id"]),
          )
      )
  ```

- When you map items manually, capture loop variables with default arguments to avoid late binding.
  ```python
  @ps.component
  def Toolbar(items: list[dict], on_remove):
      return ps.div(
          *[
              ps.button(
                  f"Remove {item['label']}",
                  onClick=lambda _, item_id=item["id"]: on_remove(item_id),
                  key=item["id"],
              )
              for item in items
          ]
      )
  ```

## Shared State
- Use `ps.global_state` to share state across components within the same page. Call the factory it returns from any component that needs that shared state. Pass in an optional key to create different instances.
  ```python
  import pulse as ps

  class Settings(ps.State):
      theme: str = "light"

      def set_theme(self, value: str):
          self.theme = value

  page_settings = ps.global_state(lambda: Settings())

  @ps.component
  def SettingsPanel():
      settings = page_settings()
      return ps.select(
          value=settings.theme,
          onChange=lambda event: settings.set_theme(event["target"]["value"]),
          children=[
              ps.option("light", value="light"),
              ps.option("dark", value="dark"),
          ],
      )
  ```

## Forms
- Use `ps.Form` for auto-managed submissions. The `onSubmit` handler receives a `ps.FormData` mapping (values or lists for repeated fields) and can be sync or async.
  ```python
  import pulse as ps

  class Feedback(ps.State):
      last_message: str = ""

      async def handle_submit(self, data: ps.FormData):
          self.last_message = data["message"]

  @ps.component
  def FeedbackForm():
      state = ps.states(lambda: Feedback())
      return ps.div(
          ps.Form(onSubmit=state.handle_submit)[
              ps.label("Message", htmlFor="feedback"),
              ps.textarea(id="feedback", name="message"),
              ps.button("Send", type="submit"),
          ],
          ps.p(f"Last message: {state.last_message}") if state.last_message else None,
      )
  ```

- Reach for `ps.ManualForm` when you need granular control (e.g., progressive validation or custom network calls). Create it once, spread its props onto a plain `ps.form`, and drive submission yourself.
  ```python
  @ps.component
  def ManualUpload():
      state = ps.states(lambda: Feedback())
      manual_form = ps.setup(lambda: ps.ManualForm(state.handle_submit))
      props = manual_form.props()
      return ps.form(**props)[
          ps.input(type="file", name="attachment"),
          ps.button("Upload", type="submit"),
      ]
  ```

## Events & Validation
- Read browser event payloads from the event dict and validate inside state methods.
  ```python
  class EmailForm(ps.State):
      value: str = ""
      error: str | None = None

      def submit(self, email: str):
          self.error = None if "@" in email else "Invalid email"

  @ps.component
  def EmailInput():
      state = ps.states(lambda: EmailForm())
      return ps.form(
          onSubmit=lambda event: state.submit(event["target"]["value"]),
          children=[
              ps.input(type="email", value=state.value),
              ps.small(state.error) if state.error else None,
          ],
      )
  ```
