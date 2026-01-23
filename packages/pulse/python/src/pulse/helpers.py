import asyncio
import inspect
import linecache
import os
import socket
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import (
	Any,
	ParamSpec,
	Self,
	TypedDict,
	TypeVar,
	overload,
	override,
)
from urllib.parse import urlsplit

from anyio import from_thread
from fastapi import Request

from pulse.env import env


def values_equal(a: Any, b: Any) -> bool:
	"""Robust equality that avoids ambiguous truth for DataFrames/ndarrays.

	Strategy:
	- identity check fast-path
	- try a == b / != comparison
	- if comparison raises or returns a non-bool (e.g., array-like), fall back to False
	"""
	if a is b:
		return True
	try:
		result = a == b
	except Exception:
		return False
	# Some libs return array-like; only accept plain bools
	if isinstance(result, bool):
		return result
	return False


def getsourcecode(obj: Any) -> str:
	"""Get source code for an object, handling stale cache issues after module renames.

	This is a wrapper around inspect.getsource() that handles cases where the
	linecache has stale entries after module renames or when source files have moved.
	"""
	# Try to get source first without clearing cache (common case)
	try:
		return inspect.getsource(obj)
	except OSError:
		# If that fails, it might be a stale cache issue after module rename
		# Clear cache and try again
		linecache.clearcache()
		try:
			return inspect.getsource(obj)
		except OSError:
			# Still failing - code object might have a stale filename
			# Get the actual source file from the module and update cache manually
			module = inspect.getmodule(obj)
			if module and hasattr(module, "__file__") and module.__file__:
				module_file = module.__file__
				if module_file.endswith(".pyc"):
					module_file = module_file[:-1]
				if os.path.exists(module_file):
					# Read the file and update cache with code object's filename
					with open(module_file, "r", encoding="utf-8") as f:
						lines = f.readlines()
					code_filename = obj.__code__.co_filename
					linecache.cache[code_filename] = (
						len(lines),
						None,
						lines,
						code_filename,
					)
					# Try again after updating cache
					return inspect.getsource(obj)
			raise


T = TypeVar("T")
P = ParamSpec("P")

# In case we refine it later
CSSProperties = dict[str, Any]


class Missing:
	__slots__: tuple[str, ...] = ()

	@override
	def __repr__(self) -> str:
		return "MISSING"


MISSING = Missing()


class File(TypedDict):
	name: str
	type: str
	"Indicates the MIME type of the data. If the type is unknown, the string is empty."
	size: int
	last_modified: int
	"Last modified time of the file, in millisecond since the UNIX epoch"
	contents: bytes


class Sentinel:
	name: str
	value: Any

	def __init__(self, name: str, value: Any = MISSING) -> None:
		self.name = name
		self.value = value

	def __call__(self, value: Any):
		return Sentinel(self.name, value)

	@override
	def __repr__(self) -> str:
		if self.value is not MISSING:
			return f"{self.name}({self.value})"
		else:
			return self.name


def data(**attrs: Any):
	"""Helper to pass data attributes as keyword arguments to Pulse elements.

	Example:
	    data(foo="bar") -> {"data-foo": "bar"}
	"""
	return {f"data-{k}": v for k, v in attrs.items()}


# --- Async scheduling helpers (work from loop or sync threads) ---
class Disposable(ABC):
	__disposed__: bool = False

	@abstractmethod
	def dispose(self) -> None: ...

	def __init_subclass__(cls, **kwargs: Any):
		super().__init_subclass__(**kwargs)

		if "dispose" in cls.__dict__:
			original_dispose = cls.dispose

			@wraps(original_dispose)
			def wrapped_dispose(self: Self, *args: Any, **kwargs: Any):
				if self.__disposed__:
					if env.pulse_env == "dev":
						cls_name = type(self).__name__
						raise RuntimeError(
							f"{self} (type={cls_name}) was disposed twice. This is likely a bug."
						)
					return
				self.__disposed__ = True
				return original_dispose(self, *args, **kwargs)

			cls.dispose = wrapped_dispose


def is_pytest() -> bool:
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
			if not is_pytest():
				raise


def create_task(
	coroutine: Awaitable[T],
	*,
	name: str | None = None,
	on_done: Callable[[asyncio.Task[T]], None] | None = None,
) -> asyncio.Task[T]:
	"""Create and schedule a coroutine task on the main loop from any thread.

	- factory should create a fresh coroutine each call
	- optional on_done is attached on the created task within the loop
	"""

	try:
		asyncio.get_running_loop()
		# ensure_future accepts Awaitable and returns a Task when given a coroutine
		task = asyncio.ensure_future(coroutine)
		if name is not None:
			task.set_name(name)
		if on_done:
			task.add_done_callback(on_done)
		return task
	except RuntimeError:

		async def _runner():
			asyncio.get_running_loop()
			# ensure_future accepts Awaitable and returns a Task when given a coroutine
			task = asyncio.ensure_future(coroutine)
			if name is not None:
				task.set_name(name)
			if on_done:
				task.add_done_callback(on_done)
			return task

		try:
			return from_thread.run(_runner)
		except RuntimeError:
			if is_pytest():
				return None  # pyright: ignore[reportReturnType]
			raise


def create_future_on_loop() -> asyncio.Future[Any]:
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

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.
	"""

	from pulse.reactive import Untrack

	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		try:
			loop = asyncio.get_event_loop()
		except RuntimeError as exc:
			raise RuntimeError("later() requires an event loop") from exc

	def _run():
		try:
			with Untrack():
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
	task: asyncio.Task[None] | None
	cancelled: bool

	def __init__(self) -> None:
		self.task = None
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

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.

	Optional kwargs:
	- immediate: bool = False  # run once immediately before the first interval
	"""

	from pulse.reactive import Untrack

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
					with Untrack():
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
	  1) Origin header (full scheme://host:port)
	  1b) Referer header (full URL) when Origin missing
	  2) Forwarded header (proto + for)
	  3) X-Forwarded-* headers
	  4) Host header (server address the client connected to)
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

		# Fallback: use Host header which contains the server address the client connected to
		host_header = request.headers.get("host")
		if host_header:
			return f"{proto}://{host_header}"
		return None
	except Exception:
		return None


def get_client_address_socketio(environ: dict[str, Any]) -> str | None:
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

		# Fallback: use HTTP_HOST which contains the server address the client connected to
		host_header = environ.get("HTTP_HOST")
		if host_header:
			return f"{proto}://{host_header}"
		return None
	except Exception:
		return None


# --- Runtime lock helpers moved to pulse.cli.web_lock ---
# Use WebLock context manager for idempotent lock management


@overload
def call_flexible(
	handler: Callable[..., Awaitable[T]], *payload_args: Any
) -> Awaitable[T]: ...
@overload
def call_flexible(handler: Callable[..., T], *payload_args: Any) -> T: ...
def call_flexible(handler: Callable[..., Any], *payload_args: Any) -> Any:
	"""
	Call handler with a trimmed list of positional args based on its signature; await if needed.

	- If the handler accepts *args, pass all payload_args.
	- Otherwise, pass up to N positional args where N is the number of positional params.
	- If inspection fails, pass payload_args as-is.
	- Any exceptions raised by the handler are swallowed (best-effort callback semantics).
	"""
	try:
		sig = inspect.signature(handler)
		params = list(sig.parameters.values())
		has_var_pos = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
		if has_var_pos:
			args_to_pass = payload_args
		else:
			nb_positional = 0
			for p in params:
				if p.kind in (
					inspect.Parameter.POSITIONAL_ONLY,
					inspect.Parameter.POSITIONAL_OR_KEYWORD,
				):
					nb_positional += 1
			args_to_pass = payload_args[:nb_positional]
	except Exception:
		# If inspection fails, default to passing the payload as-is
		args_to_pass = payload_args

	return handler(*args_to_pass)


async def maybe_await(value: T | Awaitable[T]) -> T:
	if inspect.isawaitable(value):
		return await value
	return value


def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
	"""Find an available port starting from start_port."""
	for port in range(start_port, start_port + max_attempts):
		# First check if something is actively listening on the port
		# by trying to connect to it (check both IPv4 and IPv6)
		port_in_use = False
		for family, addr in [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")]:
			try:
				with socket.socket(family, socket.SOCK_STREAM) as test_socket:
					test_socket.settimeout(0.1)
					result = test_socket.connect_ex((addr, port))
					# If connection succeeds (result == 0), something is listening
					if result == 0:
						port_in_use = True
						break
			except OSError:
				# Connection failed, continue checking
				pass

		if port_in_use:
			continue

		# Port appears free, try to bind to it
		# Allow reuse of addresses in TIME_WAIT state (matches uvicorn behavior)
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
				s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
				s.bind(("localhost", port))
				return port
		except OSError:
			continue
	raise RuntimeError(
		f"Could not find an available port after {max_attempts} attempts starting from {start_port}"
	)
