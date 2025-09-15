import asyncio
import json
import os
from pathlib import Path
import platform
import socket
import time
from typing import (
    Any,
    Callable,
    Coroutine,
    Iterable,
    ParamSpec,
    Protocol,
    TypedDict,
    TypeVar,
    TypeVarTuple,
    Unpack,
)
from urllib.parse import urlsplit
from anyio import from_thread

from fastapi import Request

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


class File(TypedDict):
    name: str
    type: str
    "Indicates the MIME type of the data. If the type is unknown, the string is empty."
    size: int
    last_modified: int
    "Last modified time of the file, in millisecond since the UNIX epoch"
    contents: bytes


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


# --- Async scheduling helpers (work from loop or sync threads) ---


def _running_under_pytest() -> bool:
    """Detect if running inside pytest using environment variables."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
        "PYTEST_XDIST_TESTRUNUID" in os.environ
    )


def schedule_on_loop(callback: Callable[[], None]) -> None:
    """Schedule a callback to run ASAP on the main event loop from any thread."""
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(callback)
    except RuntimeError:

        async def _runner():
            loop = asyncio.get_running_loop()
            loop.call_soon(callback)

        try:
            from_thread.run(_runner)
        except RuntimeError:
            if not _running_under_pytest():
                raise


def create_task(
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    name: str | None = None,
    on_done: Callable[[asyncio.Task[Any]], None] | None = None,
) -> None:
    """Create and schedule a coroutine task on the main loop from any thread.

    - factory should create a fresh coroutine each call
    - optional on_done is attached on the created task within the loop
    """

    def _schedule() -> None:
        loop = asyncio.get_running_loop()
        try:
            task = loop.create_task(factory(), name=name)
        except TypeError:
            task = loop.create_task(factory())
        if on_done is not None:
            task.add_done_callback(on_done)

    from_thread.run

    schedule_on_loop(_schedule)


def create_future_on_loop() -> asyncio.Future:
    """Create an asyncio Future on the main event loop from any thread."""
    try:
        return asyncio.get_running_loop().create_future()
    except RuntimeError:
        from anyio import from_thread

        async def _create():
            loop = asyncio.get_running_loop()
            return loop.create_future()

        return from_thread.run(_create)


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


def get_client_address(request: Request) -> str | None:
    """Best-effort client origin/address from an HTTP request.

    Preference order:
      1) Origin (full scheme://host:port)
      1b) Referer (full URL) when Origin missing during prerender forwarding
      2) Forwarded header (proto + for)
      3) X-Forwarded-* headers
      4) request.client host:port
    """
    try:
        origin = request.headers.get("origin")
        if origin:
            return origin
        referer = request.headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"

        fwd = request.headers.get("forwarded")
        proto = request.headers.get("x-forwarded-proto") or (
            [p.split("proto=")[-1] for p in fwd.split(";") if "proto=" in p][0]
            .strip()
            .strip('"')
            if fwd and "proto=" in fwd
            else request.url.scheme
        )
        if fwd and "for=" in fwd:
            part = [p for p in fwd.split(";") if "for=" in p]
            hostport = part[0].split("for=")[-1].strip().strip('"') if part else ""
            if hostport:
                return f"{proto}://{hostport}"

        xff = request.headers.get("x-forwarded-for")
        xfp = request.headers.get("x-forwarded-port")
        if xff:
            host = xff.split(",")[0].strip()
            if host in ("127.0.0.1", "::1"):
                host = "localhost"
            return f"{proto}://{host}:{xfp}" if xfp else f"{proto}://{host}"

        host = request.client.host if request.client else ""
        port = request.client.port if request.client else None
        if host in ("127.0.0.1", "::1"):
            host = "localhost"
        if host and port:
            return f"{proto}://{host}:{port}"
        if host:
            return f"{proto}://{host}"
        return None
    except Exception:
        return None


def get_client_address_socketio(environ: dict) -> str | None:
    """Best-effort client origin/address from a WS environ mapping.

    Preference order mirrors HTTP variant using environ keys.
    """
    try:
        origin = environ.get("HTTP_ORIGIN")
        if origin:
            return origin

        fwd = environ.get("HTTP_FORWARDED")
        proto = environ.get("HTTP_X_FORWARDED_PROTO") or (
            [p.split("proto=")[-1] for p in str(fwd).split(";") if "proto=" in p][0]
            .strip()
            .strip('"')
            if fwd and "proto=" in str(fwd)
            else environ.get("wsgi.url_scheme", "http")
        )
        if fwd and "for=" in str(fwd):
            part = [p for p in str(fwd).split(";") if "for=" in p]
            hostport = part[0].split("for=")[-1].strip().strip('"') if part else ""
            if hostport:
                return f"{proto}://{hostport}"

        xff = environ.get("HTTP_X_FORWARDED_FOR")
        xfp = environ.get("HTTP_X_FORWARDED_PORT")
        if xff:
            host = str(xff).split(",")[0].strip()
            if host in ("127.0.0.1", "::1"):
                host = "localhost"
            return f"{proto}://{host}:{xfp}" if xfp else f"{proto}://{host}"

        host = environ.get("REMOTE_ADDR", "")
        port = environ.get("REMOTE_PORT")
        if host in ("127.0.0.1", "::1"):
            host = "localhost"
        if host and port:
            return f"{proto}://{host}:{port}"
        if host:
            return f"{proto}://{host}"
        return None
    except Exception:
        return None


# --- Runtime lock helpers (prevent multiple dev instances per web root) ---


def _is_process_alive(pid: int) -> bool:
    try:
        # On POSIX, signal 0 checks for existence without killing
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we may not have permission
        return True
    except Exception:
        # Best-effort: assume alive if uncertain
        return True
    return True


def lock_path_for_web_root(web_root: Path, filename: str = ".pulse.lock") -> Path:
    return Path(web_root) / filename


def write_gitignore_for_lock(lock_path: Path) -> None:
    try:
        gitignore_path = lock_path.parent / ".gitignore"
        pattern = f"\n{lock_path.name}\n"
        if gitignore_path.exists():
            try:
                content = gitignore_path.read_text()
            except Exception:
                content = ""
            if lock_path.name not in content.split():
                gitignore_path.write_text(content + pattern)
        else:
            gitignore_path.write_text(pattern.lstrip("\n"))
    except Exception:
        # Non-fatal
        pass


def _read_lock(lock_path: Path) -> dict | None:
    try:
        data = json.loads(lock_path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def ensure_web_lock(lock_path: Path, *, owner: str = "server") -> tuple[Path, bool]:
    """Create a lock file or raise if an active one exists.

    Returns (lock_path, created_now)
    """
    lock_path = Path(lock_path)
    write_gitignore_for_lock(lock_path)

    if lock_path.exists():
        info = _read_lock(lock_path) or {}
        pid = int(info.get("pid", 0) or 0)
        if pid and _is_process_alive(pid):
            raise RuntimeError(
                f"Another Pulse dev instance appears to be running (pid={pid}) for {lock_path.parent}."
            )
        # Stale lock; continue to overwrite

    payload = {
        "pid": os.getpid(),
        "owner": owner,
        "created_at": int(time.time()),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
    }
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(payload))
    except Exception as exc:
        raise RuntimeError(f"Failed to create lock file at {lock_path}: {exc}")
    return lock_path, True


def validate_existing_lock(lock_path: Path) -> bool:
    """Validate an existing lock. Returns True if an active other instance exists.

    If the file is missing or stale, returns False. If an active other instance is
    detected, raises RuntimeError.
    """
    lock_path = Path(lock_path)
    if not lock_path.exists():
        return False
    info = _read_lock(lock_path) or {}
    pid = int(info.get("pid", 0) or 0)
    if pid and _is_process_alive(pid):
        # Active lock
        raise RuntimeError(
            f"Another Pulse dev instance appears to be running (pid={pid}) for {lock_path.parent}."
        )
    return False


def remove_web_lock(lock_path: Path) -> None:
    try:
        Path(lock_path).unlink(missing_ok=True)
    except Exception:
        # Best-effort cleanup
        pass
