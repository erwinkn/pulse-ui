from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass
from typing import TYPE_CHECKING, Any, Literal, TypedDict
from urllib.parse import urlparse

from fastapi import Request, Response

from pulse.hooks.runtime import set_cookie

if TYPE_CHECKING:
	from pulse.app import PulseMode


@dataclass
class Cookie:
	name: str
	_: KW_ONLY
	domain: str | None = None
	secure: bool = True
	samesite: Literal["lax", "strict", "none"] = "lax"
	max_age_seconds: int = 7 * 24 * 3600

	def get_from_fastapi(self, request: Request) -> str | None:
		"""Extract sid from a FastAPI Request (by reading Cookie header)."""
		header = request.headers.get("cookie")
		cookies = parse_cookie_header(header)
		return cookies.get(self.name)

	def get_from_socketio(self, environ: dict[str, Any]) -> str | None:
		"""Extract sid from a socket.io environ mapping."""
		raw = environ.get("HTTP_COOKIE") or environ.get("COOKIE")
		cookies = parse_cookie_header(raw)
		return cookies.get(self.name)

	async def set_through_api(self, value: str):
		await set_cookie(
			name=self.name,
			value=value,
			domain=self.domain,
			secure=self.secure,
			samesite=self.samesite,
			max_age_seconds=self.max_age_seconds,
		)

	def set_on_fastapi(self, response: Response, value: str) -> None:
		"""Set the session cookie on a FastAPI Response-like object."""
		response.set_cookie(
			key=self.name,
			value=value,
			httponly=True,
			samesite=self.samesite,
			secure=self.secure,
			max_age=self.max_age_seconds,
			domain=self.domain,
			path="/",
		)


@dataclass
class SetCookie(Cookie):
	value: str

	@classmethod
	def from_cookie(cls, cookie: Cookie, value: str) -> "SetCookie":
		return cls(
			name=cookie.name,
			value=value,
			domain=cookie.domain,
			secure=cookie.secure,
			samesite=cookie.samesite,
			max_age_seconds=cookie.max_age_seconds,
		)


def session_cookie(
	mode: "PulseMode",
	name: str = "pulse.sid",
	max_age_seconds: int = 7 * 24 * 3600,
):
	if mode == "single-server":
		return Cookie(
			name,
			domain=None,
			secure=False,
			samesite="lax",
			max_age_seconds=max_age_seconds,
		)
	elif mode == "subdomains":
		return Cookie(
			name,
			domain=None,  # to be set later
			secure=True,
			samesite="lax",
			max_age_seconds=max_age_seconds,
		)
	else:
		raise ValueError(f"Unexpected cookie mode: '{mode}'")


class CORSOptions(TypedDict, total=False):
	allow_origins: Sequence[str]
	"List of allowed origins. Use ['*'] to allow all origins. Default: ()"

	allow_methods: Sequence[str]
	"List of allowed HTTP methods. Use ['*'] to allow all methods. Default: ('GET',)"

	allow_headers: Sequence[str]
	"List of allowed HTTP headers. Use ['*'] to allow all headers. Default: ()"

	allow_credentials: bool
	"Whether to allow credentials (cookies, authorization headers etc). Default: False"

	allow_origin_regex: str | None
	"Regex pattern for allowed origins. Alternative to allow_origins list. Default: None"

	expose_headers: Sequence[str]
	"List of headers to expose to the browser. Default: ()"

	max_age: int
	"How long browsers should cache CORS responses, in seconds. Default: 600"


def _parse_host(server_address: str) -> str | None:
	try:
		if not server_address:
			return None
		host = urlparse(server_address).hostname
		return host
	except Exception:
		return None


def _base_domain(host: str) -> str:
	# Simplified rule: drop the leftmost label, keep everything to the right.
	# Assumes host is a subdomain (e.g., api.example.com -> example.com).
	i = host.find(".")
	return host[i + 1 :] if i != -1 else host


def compute_cookie_domain(mode: "PulseMode", server_address: str) -> str | None:
	host = _parse_host(server_address)
	if mode == "single-server" or not host:
		return None
	if mode == "subdomains":
		return "." + _base_domain(host)
	return None


def cors_options(mode: "PulseMode", server_address: str) -> CORSOptions:
	host = _parse_host(server_address) or "localhost"
	opts: CORSOptions = {
		"allow_credentials": True,
		"allow_methods": ["*"],
		"allow_headers": ["*"],
	}
	if mode == "subdomains":
		base = _base_domain(host)
		# Escape dots in base domain for regex (doesn't affect localhost since it has no dots)
		base = base.replace(".", r"\.")
		# Allow any subdomain and any port for the base domain
		opts["allow_origin_regex"] = rf"^https?://([a-z0-9-]+\\.)?{base}(:\\d+)?$"
		return opts
	elif mode == "single-server":
		# For single-server mode, allow same origin
		# Escape dots in host for regex (doesn't affect localhost since it has no dots)
		host = host.replace(".", r"\.")
		opts["allow_origin_regex"] = rf"^https?://{host}(:\\d+)?$"
		return opts
	else:
		raise ValueError(f"Unsupported deployment mode '{mode}'")


def parse_cookie_header(header: str | None) -> dict[str, str]:
	cookies: dict[str, str] = {}
	if not header:
		return cookies
	parts = [p.strip() for p in header.split(";") if p.strip()]
	for part in parts:
		if "=" in part:
			k, v = part.split("=", 1)
			cookies[k.strip()] = v.strip()
	return cookies
