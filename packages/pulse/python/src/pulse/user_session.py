import base64
import hmac
import json
import logging
import secrets
import uuid
import zlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast, override

from fastapi import Response

from pulse.cookies import SetCookie
from pulse.env import env
from pulse.helpers import Disposable
from pulse.reactive import AsyncEffect, Effect
from pulse.reactive_extensions import ReactiveDict, reactive, unwrap

if TYPE_CHECKING:
	from pulse.app import App

Session = ReactiveDict[str, Any]

logger = logging.getLogger(__name__)


class UserSession(Disposable):
	sid: str
	data: Session
	app: "App"
	is_cookie_session: bool
	_queued_cookies: dict[str, SetCookie]
	scheduled_cookie_refresh: bool
	_effect: Effect | AsyncEffect

	def __init__(self, sid: str, data: dict[str, Any], app: "App") -> None:
		self.sid = sid
		self.data = reactive(data)
		self.scheduled_cookie_refresh = False
		self._queued_cookies = {}
		self.app = app
		self.is_cookie_session = isinstance(app.session_store, CookieSessionStore)
		if isinstance(app.session_store, CookieSessionStore):
			self._effect = Effect(
				lambda: self.refresh_session_cookie(app),
				name=f"save_cookie_session:{self.sid}",
			)
		else:
			self._effect = AsyncEffect(
				self._save_server_session, name=f"save_server_session:{self.sid}"
			)

	async def _save_server_session(self):
		assert isinstance(self.app.session_store, SessionStore)
		# unwrap subscribes the effect to all signals in the session ReactiveDict
		data = unwrap(self.data)
		await self.app.session_store.save(self.sid, data)

	def refresh_session_cookie(self, app: "App"):
		assert isinstance(app.session_store, CookieSessionStore)
		# unwrap subscribes the effect to all signals in the session ReactiveDict
		data = unwrap(self.data)
		signed_cookie = app.session_store.encode(self.sid, data)
		self.set_cookie(
			name=app.cookie.name,
			value=signed_cookie,
			domain=app.cookie.domain,
			secure=app.cookie.secure,
			samesite=app.cookie.samesite,
			max_age_seconds=app.cookie.max_age_seconds,
		)

	@override
	def dispose(self):
		self._effect.dispose()

	def handle_response(self, res: Response):
		# For cookie sessions, run the effect now if it's scheduled, in order to set the updated cookie
		if self.is_cookie_session:
			self._effect.flush()
		for cookie in self._queued_cookies.values():
			cookie.set_on_fastapi(res, cookie.value)
		self._queued_cookies.clear()
		self.scheduled_cookie_refresh = False

	def set_cookie(
		self,
		name: str,
		value: str,
		domain: str | None = None,
		secure: bool = True,
		samesite: Literal["lax", "strict", "none"] = "lax",
		max_age_seconds: int = 7 * 24 * 3600,
	):
		cookie = SetCookie(
			name=name,
			value=value,
			domain=domain,
			secure=secure,
			samesite=samesite,
			max_age_seconds=max_age_seconds,
		)
		self._queued_cookies[name] = cookie
		if not self.scheduled_cookie_refresh:
			self.app.refresh_cookies(self.sid)
			self.scheduled_cookie_refresh = True


class SessionStore(ABC):
	"""Abstract base for server-backed session stores (DB, cache, memory).

	Implementations persist session state on the server and place only a stable
	identifier in the cookie. Override methods to integrate with your backend.
	"""

	async def init(self) -> None:
		"""Optional async initializer, invoked when the app starts.

		Override in implementations that need to establish connections or
		perform startup work. Default is a no-op.
		"""
		return None

	async def close(self) -> None:
		"""Optional async cleanup, invoked when the app shuts down.

		Override in implementations that need to tear down connections or
		perform cleanup. Default is a no-op.
		"""
		return None

	@abstractmethod
	async def get(self, sid: str) -> dict[str, Any] | None: ...

	@abstractmethod
	async def create(self, sid: str) -> dict[str, Any]: ...

	@abstractmethod
	async def delete(self, sid: str) -> None: ...

	@abstractmethod
	async def save(self, sid: str, session: dict[str, Any]) -> None: ...


class InMemorySessionStore(SessionStore):
	def __init__(self) -> None:
		self._sessions: dict[str, dict[str, Any]] = {}

	@override
	async def get(self, sid: str) -> dict[str, Any] | None:
		return self._sessions.get(sid)

	@override
	async def create(self, sid: str) -> dict[str, Any]:
		session: Session = ReactiveDict()
		self._sessions[sid] = session
		return session

	@override
	async def save(self, sid: str, session: dict[str, Any]):
		# Should not matter as the session ReactiveDict is normally mutated directly
		self._sessions[sid] = session

	@override
	async def delete(self, sid: str) -> None:
		_ = self._sessions.pop(sid, None)


class SessionCookiePayload(TypedDict):
	sid: str
	data: dict[str, Any]


class CookieSessionStore:
	"""Persist session in a signed cookie (Flask-like default).

	The cookie stores a compact JSON of the session and is signed using
	HMAC-SHA256 to prevent tampering. Keep the session small (<4KB).
	"""

	digestmod: str
	secret: bytes
	salt: bytes
	max_cookie_bytes: int

	def __init__(
		self,
		secret: str | None = None,
		*,
		salt: str = "pulse.session",
		digestmod: str = "sha256",
		max_cookie_bytes: int = 3800,
	) -> None:
		if not secret:
			secret = env.pulse_secret or ""
			if not secret:
				pulse_env = env.pulse_env
				if pulse_env == "prod":
					# In CI/production, require an explicit secret
					raise RuntimeError(
						"PULSE_SECRET must be set when using CookieSessionStore in production.\nCookieSessionStore is the default way of storing sessions in Pulse. Providing a secret is necessary to not invalidate all sessions on reload."
					)
				# In dev, use an ephemeral secret silently
				secret = secrets.token_urlsafe(32)
		self.secret = secret.encode("utf-8")
		self.salt = salt.encode("utf-8")
		self.digestmod = digestmod
		self.max_cookie_bytes = max_cookie_bytes

	def encode(self, sid: str, session: dict[str, Any]) -> str:
		# Encode the entire session into the cookie (compressed v1)
		try:
			data = SessionCookiePayload(sid=sid, data=dict(session))
			payload_json = json.dumps(data, separators=(",", ":")).encode("utf-8")
			compressed = zlib.compress(payload_json, level=6)
			signed = self._sign(compressed)
			if len(signed) > self.max_cookie_bytes:
				logging.warning("Session cookie too large, truncating")
				session.clear()
				return self.encode(sid, session)
			return signed
		except Exception:
			logging.warning("Error encoding session cookie, truncating")
			session.clear()
			return self.encode(sid, session)

	def decode(self, cookie: str) -> tuple[str, Session] | None:
		"""Decode a signed session cookie (compressed v1)."""
		if not cookie:
			return None

		raw = self._unsign(cookie)
		if raw is None:
			return None

		try:
			payload_json = zlib.decompress(raw).decode("utf-8")
			data = cast(SessionCookiePayload, json.loads(payload_json))
			return data["sid"], ReactiveDict(data["data"])
		except Exception:
			return None

	# --- signing helpers ---
	def _mac(self, payload: bytes) -> bytes:
		return hmac.new(
			self.secret + b"|" + self.salt, payload, self.digestmod
		).digest()

	def _sign(self, payload: bytes) -> str:
		mac = self._mac(payload)
		b64 = base64.urlsafe_b64encode(payload).rstrip(b"=")
		sig = base64.urlsafe_b64encode(mac).rstrip(b"=")
		return f"v1.{b64.decode('ascii')}.{sig.decode('ascii')}"

	def _unsign(self, token: str) -> bytes | None:
		try:
			if not token.startswith("v1."):
				return None
			_, b64, sig = token.split(".", 2)

			def _pad(s: str) -> bytes:
				return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

			raw = _pad(b64)
			mac = _pad(sig)
			expected = self._mac(raw)
			if not hmac.compare_digest(mac, expected):
				return None
			return raw
		except Exception:
			return None


def new_sid() -> str:
	return uuid.uuid4().hex
