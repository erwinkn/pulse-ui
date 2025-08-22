import asyncio

from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar, cast
import uuid

from pulse.reactive import Computed, Effect, Signal, Untrack


T = TypeVar("T")


class QueryResult(Generic[T]):
    def __init__(self, initial_data: Optional[T] = None):
        # print("[QueryResult] initialize")
        self._is_loading: Signal[bool] = Signal(True, name="query.is_loading")
        self._is_error: Signal[bool] = Signal(False, name="query.is_error")
        self._error: Signal[Exception | None] = Signal(None, name="query.error")
        # Store initial data so we can preserve non-None semantics when requested
        self._initial_data: Optional[T] = initial_data
        self._data: Signal[Optional[T]] = Signal(initial_data, name="query.data")
        # Tracks whether at least one load cycle completed (success or error)
        self._has_loaded: Signal[bool] = Signal(False, name="query.has_loaded")

    @property
    def is_loading(self) -> bool:
        # print(f"[QueryResult] Accessing is_loading = {self._is_loading.read()}")
        return self._is_loading.read()

    @property
    def is_error(self) -> bool:
        # print(f"[QueryResult] Accessing is_error = {self._is_error.read()}")
        return self._is_error.read()

    @property
    def error(self) -> Exception | None:
        # print(f"[QueryResult] Accessing error = {self._error.read()}")
        return self._error.read()

    @property
    def data(self) -> Optional[T]:
        # print(f"[QueryResult] Accessing data = {self._data.read()}")
        return self._data.read()

    @property
    def has_loaded(self) -> bool:
        return self._has_loaded.read()

    # Internal setters used by the query machinery
    def _set_loading(self, *, clear_data: bool = False):
        # print("[QueryResult] set loading=True")
        self._is_loading.write(True)
        self._is_error.write(False)
        self._error.write(None)
        if clear_data:
            # If there was an explicit initial value, reset to it; otherwise clear
            self._data.write(self._initial_data)

    def _set_success(self, data: T):
        # print(f"[QueryResult] set success data={data!r}")
        self._data.write(data)
        self._is_loading.write(False)
        self._is_error.write(False)
        self._error.write(None)
        self._has_loaded.write(True)

    def _set_error(self, err: Exception):
        # print(f"[QueryResult] set error err={err!r}")
        self._error.write(err)
        self._is_loading.write(False)
        self._is_error.write(True)
        self._has_loaded.write(True)

    # Public mutator useful for optimistic updates; does not change loading/error flags
    def set_data(self, data: T):
        self._data.write(data)

    # Public mutator to set initial data before the first load completes.
    # If called after the first load, it is ignored.
    def set_initial_data(self, data: T):
        if self._has_loaded.read():
            return
        self._initial_data = data
        self._data.write(data)


class StateQuery(Generic[T]):
    def __init__(self, result: QueryResult[T], effect: Effect):
        # print("[StateQuery] create")
        self._result = result
        self._effect = effect

    # Surface API
    @property
    def is_loading(self) -> bool:
        return self._result.is_loading

    @property
    def is_error(self) -> bool:
        return self._result.is_error

    @property
    def error(self) -> Exception | None:
        return self._result.error

    @property
    def data(self) -> Optional[T]:
        return self._result.data

    @property
    def has_loaded(self) -> bool:
        return self._result.has_loaded

    def refetch(self) -> None:
        # print("[StateQuery] refetch -> schedule effect")
        # If we use .schedule(), the effect may not rerun if the query key hasn't changed
        self._effect.run()

    def dispose(self) -> None:
        # print("[StateQuery] dispose")
        self._effect.dispose()

    def set_data(self, data: T) -> None:
        self._result.set_data(data)

    def set_initial_data(self, data: T) -> None:
        self._result.set_initial_data(data)


class QueryProperty(Generic[T]):
    """
    Descriptor for state-bound queries.

    Usage:
        class S(ps.State):
            @ps.query()
            async def user(self) -> User: ...

            @user.key
            def _user_key(self):
                return ("user", self.user_id)
    """

    def __init__(
        self,
        name: str,
        fetch_fn: "Callable[[Any], Awaitable[T]]",
        keep_alive: bool = False,
        keep_previous_data: bool = True,
        initial: Optional[T] = None,
    ):
        self.name = name
        self.fetch_fn = fetch_fn
        self.key_fn: Optional[Callable[[Any], tuple]] = None
        self.keep_alive = keep_alive
        self.keep_previous_data = keep_previous_data
        self.initial = initial
        self._priv_query = f"__query_{name}"
        self._priv_effect = f"__query_effect_{name}"
        self._priv_key_comp = f"__query_key_{name}"

    # Decorator to attach a key function
    def key(self, fn: Callable[[Any], tuple]):
        self.key_fn = fn
        return fn

    def initialize(self, obj: Any) -> StateQuery[T]:
        # Return cached query instance if present
        query: Optional[StateQuery[T]] = getattr(obj, self._priv_query, None)
        if query:
            # print(f"[QueryProperty:{self.name}] return cached StateQuery")
            return query

        if self.key_fn is None:
            raise RuntimeError(
                f"State query '{self.name}' is missing a '@{self.name}.key' definition"
            )

        # Bind methods to this instance
        bound_fetch = self.fetch_fn.__get__(obj, obj.__class__)
        bound_key_fn = self.key_fn.__get__(obj, obj.__class__)
        # print(f"[QueryProperty:{self.name}] bound fetch and key functions")

        result = QueryResult[T](initial_data=self.initial)

        def compute_key():
            k = bound_key_fn()
            # print(f"[QueryProperty:{self.name}] compute key -> {k!r}")
            return k

        key_computed = Computed(compute_key, name=f"query.key.{self.name}")
        setattr(obj, self._priv_key_comp, key_computed)

        def run_effect():
            # print(f"[QueryProperty:{self.name}] effect RUN")
            key = key_computed()
            # print(f"[QueryProperty:{self.name}] effect key={key!r}")

            # Start fetch in the event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop; skip fetch and mark as error for now
                result._set_error(RuntimeError("No running event loop for query fetch"))
                return

            # Set loading immediately; optionally clear previous data
            result._set_loading(clear_data=not self.keep_previous_data)

            # Create a background task for the user async function
            with Untrack():
                unique_id = uuid.uuid4().hex[:8]
                task = loop.create_task(
                    bound_fetch(), name=f"query:{self.name}:{key}:{unique_id}"
                )
            # print(
            #     f"[QueryProperty:{self.name}] scheduled task={task.get_name()} running={not task.done()}"
            # )

            def on_done(fut: asyncio.Task):
                try:
                    data = fut.result()
                except asyncio.CancelledError:
                    # print(f"[QueryProperty:{self.name}] task cancelled")
                    return
                except Exception as e:  # noqa: BLE001
                    # print(f"[QueryProperty:{self.name}] task error -> {e!r}")
                    result._set_error(e)
                else:
                    # print(f"[QueryProperty:{self.name}] task success -> {data!r}")
                    result._set_success(data)

            task.add_done_callback(on_done)

            def cleanup() -> None:
                # print(f"[QueryProperty:{self.name}] cleanup")
                if task and not task.done():
                    # print(
                    #     f"[QueryProperty:{self.name}] cleanup -> cancel task {task.get_name()}"
                    # )
                    task.cancel()

            return cleanup

        effect = Effect(run_effect, name=f"query.effect.{self.name}")
        # print(f"[QueryProperty:{self.name}] created Effect name={effect.name}")

        # Expose the effect on the instance so State.effects() sees it
        setattr(obj, self._priv_effect, effect)

        query = StateQuery(result=result, effect=effect)
        setattr(obj, self._priv_query, query)

        if not self.keep_alive:

            def on_obs(count: int):
                if count == 0:
                    # print("[QueryProperty] Disposing of effect due to no observers")
                    effect.dispose()

            # Stop when no one observes key or data
            # result._data.on_observer_change(on_obs)
            # result._is_error.on_observer_change(on_obs)
            # result._is_loading.on_observer_change(on_obs)

        return query

    def __get__(self, obj: Any, objtype: Any = None) -> StateQuery[T]:
        if obj is None:
            return self  # type: ignore
        return self.initialize(obj)


class StateQueryNonNull(StateQuery[T]):
    @property
    def data(self) -> T:  # type: ignore[override]
        return cast(T, super().data)

    @property
    def has_loaded(self) -> bool:  # mirror base for completeness
        return super().has_loaded


class QueryPropertyWithInitial(QueryProperty[T]):
    def __get__(self, obj: Any, objtype: Any = None) -> StateQueryNonNull[T]:  # type: ignore[override]
        # Reuse base initialization but narrow the return type for type-checkers
        return cast(StateQueryNonNull[T], super().__get__(obj, objtype))
