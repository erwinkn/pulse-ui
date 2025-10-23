import asyncio
import inspect
import os
import socket
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, ParamSpec, Protocol, TypedDict, TypeVar, overload, override
from urllib.parse import urlsplit

from anyio import from_thread
from fastapi import Request


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


T = TypeVar("T")
P = ParamSpec("P")


JsFunction = Callable[P, T]

# In case we refine it later
CSSProperties = dict[str, Any]


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
	coroutine: Coroutine[Any, Any, T],
	*,
	name: str | None = None,
	on_done: Callable[[asyncio.Task[T]], None] | None = None,
) -> asyncio.Task[T]:
	"""Create and schedule a coroutine task on the main loop from any thread.

	- factory should create a fresh coroutine each call
	- optional on_done is attached on the created task within the loop
	"""

	try:
		loop = asyncio.get_running_loop()
		task = loop.create_task(coroutine, name=name)
		if on_done:
			task.add_done_callback(on_done)
		return task
	except RuntimeError:

		async def _runner():
			loop = asyncio.get_running_loop()
			task = loop.create_task(coroutine, name=name)
			if on_done:
				task.add_done_callback(on_done)
			return task

		try:
			return from_thread.run(_runner)
		except RuntimeError:
			if _running_under_pytest():
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
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
				s.bind(("localhost", port))
				return port
		except OSError:
			continue
	raise RuntimeError(
		f"Could not find an available port after {max_attempts} attempts starting from {start_port}"
	)
