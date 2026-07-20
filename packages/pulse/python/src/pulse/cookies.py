from dataclasses import KW_ONLY, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import Request, Response

from pulse.env import PulseEnv
from pulse.hooks.runtime import set_cookie


@dataclass
class Cookie:
	"""Configuration for HTTP cookies used in session management.

	Attributes:
		name: Cookie name.
		secure: HTTPS-only flag. Resolved from the runtime environment if None.
		samesite: SameSite attribute ("lax", "strict", or "none").
		max_age_seconds: Cookie lifetime in seconds (default 7 days).

	Example:
		```python
		cookie = Cookie(
			name="session",
			secure=True,
			samesite="strict",
			max_age_seconds=3600,
		)
		```
	"""

	name: str
	_: KW_ONLY
	secure: bool | None = None
	samesite: Literal["lax", "strict", "none"] = "lax"
	max_age_seconds: int = 7 * 24 * 3600

	def get_from_fastapi(self, request: Request) -> str | None:
		"""Extract cookie value from a FastAPI Request.

		Reads the Cookie header and parses it to find this cookie's value.

		Args:
			request: FastAPI/Starlette Request object.

		Returns:
			Cookie value if found, None otherwise.
		"""
		header = request.headers.get("cookie")
		cookies = parse_cookie_header(header)
		return cookies.get(self.name)

	def get_from_socketio(self, environ: dict[str, Any]) -> str | None:
		"""Extract cookie value from a Socket.IO environ mapping.

		Args:
			environ: Socket.IO environ dictionary.

		Returns:
			Cookie value if found, None otherwise.
		"""
		raw = environ.get("HTTP_COOKIE") or environ.get("COOKIE")
		cookies = parse_cookie_header(raw)
		return cookies.get(self.name)

	async def set_through_api(self, value: str) -> None:
		"""Set the cookie on the client via WebSocket.

		Must be called during a callback context.

		Args:
			value: Cookie value to set.

		Raises:
			RuntimeError: If Cookie.secure is not resolved (ensure App.setup()
				ran first).
		"""
		if self.secure is None:
			raise RuntimeError(
				"Cookie.secure is not resolved. Ensure App.setup() ran or set Cookie(secure=True/False)."
			)
		await set_cookie(
			name=self.name,
			value=value,
			secure=self.secure,
			samesite=self.samesite,
			max_age_seconds=self.max_age_seconds,
		)

	def set_on_fastapi(self, response: Response, value: str) -> None:
		"""Set the cookie on a FastAPI Response object.

		Configured with httponly=True and path="/".

		Args:
			response: FastAPI Response object.
			value: Cookie value to set.

		Raises:
			RuntimeError: If Cookie.secure is not resolved.
		"""
		if self.secure is None:
			raise RuntimeError(
				"Cookie.secure is not resolved. Ensure App.setup() ran or set Cookie(secure=True/False)."
			)
		response.set_cookie(
			key=self.name,
			value=value,
			httponly=True,
			samesite=self.samesite,
			secure=self.secure,
			max_age=self.max_age_seconds,
			path="/",
		)


@dataclass
class SetCookie(Cookie):
	"""Extended Cookie dataclass that includes the cookie value.

	Used for setting cookies with a specific value. Inherits all configuration
	from Cookie.

	Attributes:
		value: The cookie value to set.
	"""

	value: str

	@classmethod
	def from_cookie(cls, cookie: Cookie, value: str) -> "SetCookie":
		"""Create a SetCookie from an existing Cookie configuration.

		Args:
			cookie: Cookie configuration to copy settings from.
			value: Cookie value to set.

		Returns:
			SetCookie instance with the same configuration and specified value.

		Raises:
			RuntimeError: If cookie.secure is not resolved.
		"""
		if cookie.secure is None:
			raise RuntimeError(
				"Cookie.secure is not resolved. Ensure App.setup() ran or set Cookie(secure=True/False)."
			)
		return cls(
			name=cookie.name,
			value=value,
			secure=cookie.secure,
			samesite=cookie.samesite,
			max_age_seconds=cookie.max_age_seconds,
		)


def session_cookie(
	name: str = "pulse.sid",
	max_age_seconds: int = 7 * 24 * 3600,
) -> Cookie:
	return Cookie(
		name,
		secure=None,
		samesite="lax",
		max_age_seconds=max_age_seconds,
	)


def compute_cookie_secure(env: PulseEnv, public_origin: str | None) -> bool:
	if env in ("prod", "ci"):
		return True
	return urlparse(public_origin or "").scheme.lower() == "https"


def parse_cookie_header(header: str | None) -> dict[str, str]:
	"""Parse a raw Cookie header string into a dictionary.

	Args:
		header: Raw Cookie header string (e.g., "session=abc123; theme=dark").

	Returns:
		Dictionary of cookie name-value pairs.

	Example:
		```python
		cookies = parse_cookie_header("session=abc123; theme=dark")
		# {"session": "abc123", "theme": "dark"}
		```
	"""
	cookies: dict[str, str] = {}
	if not header:
		return cookies
	parts = [p.strip() for p in header.split(";") if p.strip()]
	for part in parts:
		if "=" in part:
			k, v = part.split("=", 1)
			cookies[k.strip()] = v.strip()
	return cookies
