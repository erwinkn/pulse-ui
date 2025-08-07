import asyncio

import uuid
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from pulse.reactive import Computed, Effect, Signal, untrack


T = TypeVar("T")


class QueryResult(Generic[T]):
    def __init__(self):
        print("[QueryResult] initialize")
        self._is_loading: Signal[bool] = Signal(True, name="query.is_loading")
        self._is_error: Signal[bool] = Signal(False, name="query.is_error")
        self._error: Signal[Exception | None] = Signal(None, name="query.error")
        self._data: Signal[Optional[T]] = Signal(None, name="query.data")

    @property
    def is_loading(self) -> bool:
        print(f"[QueryResult] Accessing is_loading = {self._is_loading.read()}")
        return self._is_loading.read()

    @property
    def is_error(self) -> bool:
        return self._is_error.read()

    @property
    def error(self) -> Exception | None:
        return self._error.read()

    @property
    def data(self) -> Optional[T]:
        return self._data.read()

    # Internal setters used by the query machinery
    def _set_loading(self):
        print("[QueryResult] set loading=True")
        self._is_loading.write(True)
        self._is_error.write(False)
        self._error.write(None)

    def _set_success(self, data: T):
        print(f"[QueryResult] set success data={data!r}")
        self._data.write(data)
        self._is_loading.write(False)
        self._is_error.write(False)
        self._error.write(None)

    def _set_error(self, err: Exception):
        print(f"[QueryResult] set error err={err!r}")
        self._error.write(err)
        self._is_loading.write(False)
        self._is_error.write(True)


class StateQuery(Generic[T]):
    def __init__(self, result: QueryResult[T], effect: Effect):
        print("[StateQuery] create")
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

    def refetch(self) -> None:
        print("[StateQuery] refetch -> schedule effect")
        # If we use .schedule(), the effect may not rerun if the query key hasn't changed
        self._effect.run()

    def dispose(self) -> None:
        print("[StateQuery] dispose")
        self._effect.dispose()


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

    def __init__(self, name: str, fetch_fn: "Callable[[Any], Awaitable[T]]"):
        self.name = name
        self.fetch_fn = fetch_fn
        self.key_fn: Optional[Callable[[Any], tuple]] = None
        self._priv_query = f"__query_{name}"
        self._priv_effect = f"__query_effect_{name}"

    # Decorator to attach a key function
    def key(self, fn: Callable[[Any], tuple]):
        self.key_fn = fn
        return fn

    def __get__(self, obj: Any, objtype: Any = None) -> StateQuery[T]:
        if obj is None:
            print(f"[QueryProperty:{self.name}] accessed on class")
            return self  # type: ignore

        # Return cached query instance if present
        query: Optional[StateQuery[T]] = getattr(obj, self._priv_query, None)
        if query:
            print(f"[QueryProperty:{self.name}] return cached StateQuery")
            return query

        if self.key_fn is None:
            print(f"[QueryProperty:{self.name}] missing @key")
            raise RuntimeError(
                f"State query '{self.name}' is missing a '@{self.name}.key' definition"
            )

        # Bind methods to this instance
        bound_fetch = self.fetch_fn.__get__(obj, obj.__class__)
        bound_key_fn = self.key_fn.__get__(obj, obj.__class__)  # type: ignore[union-attr]
        print(f"[QueryProperty:{self.name}] bound fetch and key functions")

        result = QueryResult[T]()

        def compute_key():
            k = bound_key_fn()
            print(f"[QueryProperty:{self.name}] compute key -> {k!r}")
            return k

        key_computed = Computed(compute_key, name=f"query.key.{self.name}")

        async def do_fetch():
            try:
                print(f"[QueryProperty:{self.name}] do_fetch start")
                result._set_loading()
                data = await bound_fetch()
                print(f"[QueryProperty:{self.name}] do_fetch success -> {data!r}")
                result._set_success(data)
            except asyncio.CancelledError:
                # Don't set error on cancellation
                print(f"[QueryProperty:{self.name}] do_fetch cancelled")
                pass
            except Exception as e:  # noqa: BLE001
                print(f"[QueryProperty:{self.name}] do_fetch error -> {e!r}")
                result._set_error(e)

        def run_effect():
            print(f"[QueryProperty:{self.name}] effect RUN")
            key = key_computed()
            print(f"[QueryProperty:{self.name}] effect key={key!r}")

            # Start fetch in the event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop; skip fetch and mark as error for now
                result._set_error(RuntimeError("No running event loop for query fetch"))
                return

            # Without untrack, the task will inherit the same ContextVar,
            # notably with the Scope object created by the effect. reactive.py
            # doesn't create a copy of the list of deps and effecs of the scope
            # before assigning them to the effect, so anything that happens in
            # this async task will be recorded as an effect dependency. This is
            # actually a very cool behavior for async, but we don't want that
            # here.
            with untrack():
                # The UUID ensures unicity of task name across reruns
                unique_id = uuid.uuid4().hex[:8]
                task = loop.create_task(
                    do_fetch(), name=f"query:{self.name}:{key}:{unique_id}"
                )
            print(
                f"[QueryProperty:{self.name}] scheduled task={task.get_name()} running={not task.done()}"
            )

            def cleanup() -> None:
                print(f"[QueryProperty:{self.name}] cleanup")
                if task and not task.done():
                    print(f"[QueryProperty:{self.name}] cleanup -> cancel task {task.get_name()}")
                    task.cancel()

            return cleanup

        effect = Effect(run_effect, name=f"query.effect.{self.name}")
        print(f"[QueryProperty:{self.name}] created Effect name={effect.name}")

        # Expose the effect on the instance so State.effects() sees it
        setattr(obj, self._priv_effect, effect)

        query = StateQuery(result=result, effect=effect)
        setattr(obj, self._priv_query, query)
        print(f"[QueryProperty:{self.name}] created StateQuery and cached on instance")
        return query
