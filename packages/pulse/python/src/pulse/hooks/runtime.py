from collections.abc import Callable, Mapping
from typing import (
	Any,
	Generic,
	Literal,
	NoReturn,
	ParamSpec,
	Protocol,
	TypeVar,
	cast,
)

from pulse.context import PulseContext
from pulse.hooks.core import HOOK_CONTEXT
from pulse.reactive_extensions import ReactiveDict
from pulse.routing import RouteContext
from pulse.state import State


class RedirectInterrupt(Exception):
	"""Exception raised to interrupt render and trigger a redirect.

	This exception is thrown by ``ps.redirect()`` to interrupt the current
	render cycle and navigate to a different path.

	Attributes:
		path: The destination URL to redirect to.
		replace: If True, replaces the current history entry instead of pushing.
	"""

	path: str
	replace: bool

	def __init__(self, path: str, *, replace: bool = False):
		super().__init__(path)
		self.path = path
		self.replace = replace


class NotFoundInterrupt(Exception):
	"""Exception raised to interrupt render and show 404 page.

	This exception is thrown by ``ps.not_found()`` to interrupt the current
	render cycle and display the 404 not found page.
	"""

	pass


def route() -> RouteContext:
	"""Get the current route context.

	Returns:
		RouteContext: Object with access to route parameters, path, and query.

	Raises:
		RuntimeError: If called outside of a component render context.

	Example:

	```python
	def user_page():
	    r = ps.route()
	    user_id = r.params.get("user_id")  # From /users/:user_id
	    page = r.query.get("page", "1")    # From ?page=2
	    return m.Text(f"User {user_id}, Page {page}")
	```
	"""
	ctx = PulseContext.get()
	if not ctx or not ctx.route:
		raise RuntimeError(
			"`pulse.route` can only be called within a component during rendering."
		)
	return ctx.route


def session() -> ReactiveDict[str, Any]:
	"""Get the current user session data.

	Returns:
		ReactiveDict[str, Any]: Reactive dictionary of session data that persists
			across page navigations.

	Raises:
		RuntimeError: If called outside of a session context.

	Example:

	```python
	def my_component():
	    sess = ps.session()
	    sess["last_visited"] = datetime.now()
	    return m.Text(f"Visits: {sess.get('visit_count', 0)}")
	```
	"""
	ctx = PulseContext.get()
	if not ctx.session:
		raise RuntimeError("Could not resolve user session")
	return ctx.session.data


def session_id() -> str:
	"""Get the current session identifier.

	Returns:
		str: Unique identifier for the current user session.

	Raises:
		RuntimeError: If called outside of a session context.
	"""
	ctx = PulseContext.get()
	if not ctx.session:
		raise RuntimeError("Could not resolve user session")
	return ctx.session.sid


def websocket_id() -> str:
	"""Get the current WebSocket connection identifier.

	Returns:
		str: Unique identifier for the current WebSocket connection.

	Raises:
		RuntimeError: If called outside of a WebSocket session context.
	"""
	ctx = PulseContext.get()
	if not ctx.render:
		raise RuntimeError("Could not resolve WebSocket session")
	return ctx.render.id


async def call_api(
	path: str,
	*,
	method: str = "POST",
	headers: Mapping[str, str] | None = None,
	body: Any | None = None,
	credentials: str = "include",
) -> dict[str, Any]:
	"""Make an API call through the client browser.

	This function sends a request to the specified path via the client's browser,
	which is useful for calling third-party APIs that require browser cookies
	or credentials.

	Args:
		path: The URL path to call.
		method: HTTP method (default: "POST").
		headers: Optional HTTP headers to include in the request.
		body: Optional request body (will be JSON serialized).
		credentials: Credential mode for the request (default: "include").

	Returns:
		dict[str, Any]: The JSON response from the API.

	Raises:
		RuntimeError: If called outside of a Pulse callback context.
	"""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("call_api() must be invoked inside a Pulse callback context")

	return await ctx.render.call_api(
		path,
		method=method,
		headers=dict(headers or {}),
		body=body,
		credentials=credentials,
	)


async def set_cookie(
	name: str,
	value: str,
	domain: str | None = None,
	secure: bool = True,
	samesite: Literal["lax", "strict", "none"] = "lax",
	max_age_seconds: int = 7 * 24 * 3600,
) -> None:
	"""Set a cookie on the client.

	Args:
		name: The cookie name.
		value: The cookie value.
		domain: Optional domain for the cookie.
		secure: Whether the cookie should only be sent over HTTPS (default: True).
		samesite: SameSite attribute ("lax", "strict", or "none"; default: "lax").
		max_age_seconds: Cookie lifetime in seconds (default: 7 days).

	Raises:
		RuntimeError: If called outside of a session context.
	"""
	ctx = PulseContext.get()
	if ctx.session is None:
		raise RuntimeError("Could not resolve the user session")
	ctx.session.set_cookie(
		name=name,
		value=value,
		domain=domain,
		secure=secure,
		samesite=samesite,
		max_age_seconds=max_age_seconds,
	)


def navigate(path: str, *, replace: bool = False, hard: bool = False) -> None:
	"""Navigate to a new URL.

	Triggers client-side navigation to the specified path. By default, uses
	client-side routing which is faster and preserves application state.

	Args:
		path: Destination URL to navigate to.
		replace: If True, replaces the current history entry instead of pushing
			a new one (default: False).
		hard: If True, performs a full page reload instead of client-side
			navigation (default: False).

	Raises:
		RuntimeError: If called outside of a Pulse callback context.

	Example:

	```python
	async def handle_login():
	    await api.login(username, password)
	    ps.navigate("/dashboard")
	```
	"""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
	ctx.render.send(
		{"type": "navigate_to", "path": path, "replace": replace, "hard": hard}
	)


def redirect(path: str, *, replace: bool = False) -> NoReturn:
	"""Redirect during render (throws exception to interrupt render).

	Unlike ``navigate()``, this function is intended for use during the render
	phase to immediately redirect before the component finishes rendering.
	It raises a ``RedirectInterrupt`` exception that is caught by the framework.

	Args:
		path: Destination URL to redirect to.
		replace: If True, replaces the current history entry instead of pushing
			a new one (default: False).

	Raises:
		RuntimeError: If called outside of component render.
		RedirectInterrupt: Always raised to interrupt the render.

	Example:

	```python
	def protected_page():
	    user = get_current_user()
	    if not user:
	        ps.redirect("/login")  # Interrupts render

	    return m.Text(f"Welcome, {user.name}")
	```
	"""
	ctx = HOOK_CONTEXT.get()
	if not ctx:
		raise RuntimeError("redirect() must be invoked during component render")
	raise RedirectInterrupt(path, replace=replace)


def not_found() -> NoReturn:
	"""Trigger 404 during render (throws exception to interrupt render).

	Interrupts the current render and displays the 404 not found page.
	Raises a ``NotFoundInterrupt`` exception that is caught by the framework.

	Raises:
		RuntimeError: If called outside of component render.
		NotFoundInterrupt: Always raised to trigger 404 page.

	Example:

	```python
	def user_page():
	    r = ps.route()
	    user = get_user(r.params["id"])
	    if not user:
	        ps.not_found()  # Shows 404 page

	    return m.Text(user.name)
	```
	"""
	ctx = HOOK_CONTEXT.get()
	if not ctx:
		raise RuntimeError("not_found() must be invoked during component render")
	raise NotFoundInterrupt()


def server_address() -> str:
	"""Get the server's public address.

	Returns:
		str: The server's public address (e.g., "https://example.com").

	Raises:
		RuntimeError: If called outside of a Pulse render/callback context
			or if the server address is not configured.
	"""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError(
			"server_address() must be called inside a Pulse render/callback context"
		)
	if not ctx.render.server_address:
		raise RuntimeError(
			"Server address unavailable. Ensure App.run_codegen/asgi_factory configured server_address."
		)
	return ctx.render.server_address


def client_address() -> str:
	"""Get the client's IP address.

	Returns:
		str: The client's IP address.

	Raises:
		RuntimeError: If called outside of a Pulse render/callback context
			or if the client address is not available.
	"""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError(
			"client_address() must be called inside a Pulse render/callback context"
		)
	if not ctx.render.client_address:
		raise RuntimeError(
			"Client address unavailable. It is set during prerender or socket connect."
		)
	return ctx.render.client_address


P = ParamSpec("P")
S = TypeVar("S", covariant=True, bound=State)


class GlobalStateAccessor(Protocol, Generic[P, S]):
	"""Protocol for global state accessor functions.

	A callable that returns the shared state instance, optionally scoped
	by an instance ID.
	"""

	def __call__(
		self, id: str | None = None, *args: P.args, **kwargs: P.kwargs
	) -> S: ...


GLOBAL_STATES: dict[str, State] = {}
"""Global dictionary storing state instances keyed by their qualified names."""


def global_state(
	factory: Callable[P, S] | type[S], key: str | None = None
) -> GlobalStateAccessor[P, S]:
	"""Create a globally shared state accessor.

	Creates a decorator or callable that provides access to a shared state
	instance. The state is shared across all components that use the same
	accessor.

	Can be used as a decorator on a State class or with a factory function.

	Args:
		factory: State class or factory function that creates the state instance.
		key: Optional custom key for the global state. If not provided, a key
			is derived from the factory's module and qualified name.

	Returns:
		GlobalStateAccessor: A callable that returns the shared state instance.
			Call with ``id=`` parameter for per-entity global state.

	Example:

	```python
	@ps.global_state
	class AppSettings(ps.State):
	    theme: str = "light"
	    language: str = "en"

	def settings_panel():
	    settings = AppSettings()  # Same instance across all components
	    return m.Select(
	        value=settings.theme,
	        data=["light", "dark"],
	        on_change=lambda v: setattr(settings, "theme", v),
	    )
	```

	With instance ID for per-entity global state:

	```python
	@ps.global_state
	class UserCache(ps.State):
	    data: dict = {}

	def user_profile(user_id: str):
	    cache = UserCache(id=user_id)  # Shared per user_id
	    return m.Text(cache.data.get("name", "Loading..."))
	```
	"""
	if isinstance(factory, type):
		cls = factory

		def _mk(*args: P.args, **kwargs: P.kwargs) -> S:
			return cast(S, cls(*args, **kwargs))

		default_key = f"{cls.__module__}:{cls.__qualname__}"
		mk = _mk
	else:
		default_key = f"{factory.__module__}:{factory.__qualname__}"
		mk = factory

	base_key = key or default_key

	def accessor(id: str | None = None, *args: P.args, **kwargs: P.kwargs) -> S:
		if id is not None:
			shared_key = f"{base_key}|{id}"
			inst = cast(S | None, GLOBAL_STATES.get(shared_key))
			if inst is None:
				inst = mk(*args, **kwargs)
				GLOBAL_STATES[shared_key] = inst
			return inst

		ctx = PulseContext.get()
		if ctx.render is None:
			raise RuntimeError(
				"ps.global_state must be called inside a Pulse render/callback context"
			)
		return cast(
			S, ctx.render.get_global_state(base_key, lambda: mk(*args, **kwargs))
		)

	return accessor


__all__ = [
	"RedirectInterrupt",
	"NotFoundInterrupt",
	"route",
	"session",
	"session_id",
	"websocket_id",
	"call_api",
	"set_cookie",
	"navigate",
	"redirect",
	"not_found",
	"server_address",
	"client_address",
	"global_state",
	"GLOBAL_STATES",
	"GlobalStateAccessor",
]
