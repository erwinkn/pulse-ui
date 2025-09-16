import asyncio
import inspect

from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar, cast

from pulse.reactive import Computed, AsyncEffect, Signal


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
    def __init__(self, result: QueryResult[T], effect: AsyncEffect):
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
        # Cancel any in-flight run and run immediately
        self._effect.cancel()
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
        self.initial_data_fn: Optional[Callable[[Any], Optional[T]]] = None
        # Single handlers; error if set more than once
        self.on_success_fn: Optional[Callable[[Any, T], Any]] = None
        self.on_error_fn: Optional[Callable[[Any, Exception], Any]] = None
        self.keep_alive = keep_alive
        self.keep_previous_data = keep_previous_data
        self.initial = initial
        self._priv_query = f"__query_{name}"
        self._priv_effect = f"__query_effect_{name}"
        self._priv_key_comp = f"__query_key_{name}"
        self._priv_initial_fn = f"__query_initial_fn_{name}"
        self._priv_initial_applied = f"__query_initial_applied_{name}"

    # Decorator to attach a key function
    def key(self, fn: Callable[[Any], tuple]):
        if self.key_fn is not None:
            raise RuntimeError(
                f"Duplicate key() decorator for query '{self.name}'. Only one is allowed."
            )
        self.key_fn = fn
        return fn

    # Decorator to attach a function providing initial data
    def initial_data(self, fn: Callable[[Any], Optional[T]]):
        if self.initial_data_fn is not None:
            raise RuntimeError(
                f"Duplicate initial_data() decorator for query '{self.name}'. Only one is allowed."
            )
        self.initial_data_fn = fn
        return fn

    # Decorator to attach an on-success handler (sync or async)
    def on_success(self, fn: Callable[[Any, T], Any]):
        if self.on_success_fn is not None:
            raise RuntimeError(
                f"Duplicate on_success() decorator for query '{self.name}'. Only one is allowed."
            )
        self.on_success_fn = fn
        return fn

    # Decorator to attach an on-error handler (sync or async)
    def on_error(self, fn: Callable[[Any, Exception], Any]):
        if self.on_error_fn is not None:
            raise RuntimeError(
                f"Duplicate on_error() decorator for query '{self.name}'. Only one is allowed."
            )
        self.on_error_fn = fn
        return fn

    def initialize(self, obj: Any) -> StateQuery[T]:
        # Return cached query instance if present
        query: Optional[StateQuery[T]] = getattr(obj, self._priv_query, None)
        if query:
            # print(f"[QueryProperty:{self.name}] return cached StateQuery")
            return query

        # key_fn being None means auto-tracked mode

        # Bind methods to this instance
        bound_fetch = self.fetch_fn.__get__(obj, obj.__class__)
        bound_on_success = (
            self.on_success_fn.__get__(obj, obj.__class__)
            if self.on_success_fn
            else None
        )
        bound_on_error = (
            self.on_error_fn.__get__(obj, obj.__class__) if self.on_error_fn else None
        )
        bound_initial_data = (
            self.initial_data_fn.__get__(obj, obj.__class__)
            if self.initial_data_fn
            else None
        )
        # print(f"[QueryProperty:{self.name}] bound fetch and key/handlers")

        # Defer evaluating initial_data provider until after user __init__ by
        # storing it on the instance and marking it unapplied. Use constructor
        # `initial` as the initial visible value for now.
        setattr(obj, self._priv_initial_fn, bound_initial_data)
        setattr(obj, self._priv_initial_applied, False)
        initial_value: Optional[T] = self.initial

        result = QueryResult[T](initial_data=initial_value)

        key_computed: Optional[Computed[tuple]] = None
        if self.key_fn:
            bound_key_fn = self.key_fn.__get__(obj, obj.__class__)

            def compute_key():
                k = bound_key_fn()
                return k

            key_computed = Computed(compute_key, name=f"query.key.{self.name}")
            setattr(obj, self._priv_key_comp, key_computed)

        inflight_key: Optional[tuple] = None

        async def run_effect():
            # print(f"[QueryProperty:{self.name}] effect RUN")
            # In key mode, deduplicate same-key concurrent reruns
            if key_computed:
                key = key_computed()

                nonlocal inflight_key
                # De-duplicate same-key concurrent reruns
                if key is not None and inflight_key == key:
                    return None
                inflight_key = key

            # Set loading immediately; optionally clear previous data
            result._set_loading(clear_data=not self.keep_previous_data)
            try:
                data = await bound_fetch()
            except asyncio.CancelledError:
                # Cancellation is expected during reruns; swallow
                return None
            except Exception as e:  # noqa: BLE001
                result._set_error(e)
                # Invoke error handler if provided
                if bound_on_error:
                    try:
                        maybe = bound_on_error(e)
                        if inspect.isawaitable(maybe):
                            await maybe
                    except Exception:
                        # Swallow handler exceptions; effect error is already recorded
                        pass
            else:
                result._set_success(data)
                # Invoke success handler if provided
                if bound_on_success:
                    try:
                        maybe = bound_on_success(data)
                        if inspect.isawaitable(maybe):
                            await maybe
                    except Exception:
                        # Swallow handler exceptions to avoid breaking effect
                        pass
            finally:
                inflight_key = None

        # In key mode, depend only on key via explicit deps
        if key_computed is not None:
            effect = AsyncEffect(
                run_effect,
                name=f"query.effect.{self.name}",
                deps=[key_computed],
            )
        else:
            effect = AsyncEffect(run_effect, name=f"query.effect.{self.name}")
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
        query = self.initialize(obj)
        # Apply initial_data provider once, after state __init__, before first load
        try:
            applied = bool(getattr(obj, self._priv_initial_applied, False))
        except Exception:
            applied = True  # fail safe: do not attempt if attribute missing
        if not applied and not query.has_loaded:
            bound_initial = getattr(obj, self._priv_initial_fn, None)
            if callable(bound_initial):
                try:
                    value = bound_initial()
                    if value is not None:
                        query.set_initial_data(value)  # type: ignore[arg-type]
                except Exception:
                    pass
            try:
                setattr(obj, self._priv_initial_applied, True)
            except Exception:
                pass
        return query


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
