import asyncio
from typing import (
    Any,
    Callable,
    Coroutine,
    Iterable,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
    Unpack,
)

from pulse.vdom import Element


Args = TypeVarTuple("Args")

T = TypeVar("T")
P = ParamSpec("P")
EventHandler = (
    Callable[[], None]
    | Callable[[], Coroutine[Any, Any, None]]
    | Callable[[Unpack[Args]], None]
    | Callable[[Unpack[Args]], Coroutine[Any, Any, None]]
)
JsFunction = Callable[P, T]

# In case we refine it later
CssStyle = dict[str, Any]


# Will be replaced by a JS transpiler type
class JsObject(Protocol): ...


MISSING = object()


class Sentinel:
    def __init__(self, name: str, value=MISSING) -> None:
        self.name = name
        self.value = value

    def __call__(self, value):
        return Sentinel(self.name, value)

    def __repr__(self) -> str:
        if self.value is not MISSING:
            return f"{self.name}({self.value})"
        else:
            return self.name


def For(items: Iterable[T], fn: Callable[[T], Element]):
    return [fn(item) for item in items]


def later(
    delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> asyncio.TimerHandle:
    """
    Schedule `fn(*args, **kwargs)` to run after `delay` seconds.
    Works with sync or async functions. Returns a TimerHandle; call .cancel() to cancel.
    """
    loop = asyncio.get_running_loop()

    def _run():
        try:
            res = fn(*args, **kwargs)
            if asyncio.iscoroutine(res):
                task = loop.create_task(res)

                def _log_task_exception(t: asyncio.Task[Any]):
                    try:
                        t.result()
                    except asyncio.CancelledError:
                        # Normal cancellation path
                        pass
                    except Exception as exc:
                        loop.call_exception_handler(
                            {
                                "message": "Unhandled exception in later() task",
                                "exception": exc,
                                "context": {"callback": fn},
                            }
                        )

                task.add_done_callback(_log_task_exception)
        except Exception as exc:
            # Surface exceptions via the loop's exception handler and continue
            loop.call_exception_handler(
                {
                    "message": "Unhandled exception in later() callback",
                    "exception": exc,
                    "context": {"callback": fn},
                }
            )

    return loop.call_later(delay, _run)

class RepeatHandle:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.cancelled = False

    def cancel(self):
        if self.cancelled:
            return
        self.cancelled = True
        if self.task is not None and not self.task.done():
            self.task.cancel()

def repeat(interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs):
    """
    Repeatedly run `fn(*args, **kwargs)` every `interval` seconds.
    Works with sync or async functions.
    For async functions, waits for completion before starting the next delay.
    Returns a handle with .cancel() to stop future runs.

    Optional kwargs:
    - immediate: bool = False  # run once immediately before the first interval
    """
    loop = asyncio.get_running_loop()
    handle = RepeatHandle()

    async def _runner():
        nonlocal handle
        try:
            while not handle.cancelled:
                # Start counting the next interval AFTER the previous execution completes
                await asyncio.sleep(interval)
                if handle.cancelled:
                    break
                try:
                    result = fn(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        await result
                except asyncio.CancelledError:
                    # Propagate to outer handler to finish cleanly
                    raise
                except Exception as exc:
                    # Surface exceptions via the loop's exception handler and continue
                    loop.call_exception_handler(
                        {
                            "message": "Unhandled exception in repeat() callback",
                            "exception": exc,
                            "context": {"callback": fn},
                        }
                    )
        except asyncio.CancelledError:
            # Swallow task cancellation to avoid noisy "exception was never retrieved"
            pass

    handle.task = loop.create_task(_runner())


    return handle
