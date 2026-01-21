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
		if app.cookie.secure is None:
			raise RuntimeError(
				"Cookie.secure is not resolved. This is likely an internal error. Ensure App.setup() ran before sessions."
			)
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

	def get_cookie_value(self, name: str) -> str | None:
		cookie = self._queued_cookies.get(name)
		if cookie is None:
			return None
		return cookie.value

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
	"""Abstract base class for server-backed session stores.

	Implementations persist session state on the server and place only a
	stable identifier in the cookie. Override methods to integrate with
	your storage backend (database, cache, memory, etc.).

	Example:
		```python
		class RedisSessionStore(SessionStore):
			async def init(self) -> None:
				self.redis = await aioredis.from_url("redis://localhost")

			async def get(self, sid: str) -> dict[str, Any] | None:
				data = await self.redis.get(f"session:{sid}")
				return json.loads(data) if data else None

			async def create(self, sid: str) -> dict[str, Any]:
				session = {}
				await self.save(sid, session)
				return session

			async def delete(self, sid: str) -> None:
				await self.redis.delete(f"session:{sid}")

			async def save(self, sid: str, session: dict[str, Any]) -> None:
				await self.redis.set(f"session:{sid}", json.dumps(session))
		```
	"""

	async def init(self) -> None:
		"""Async initialization, called on app start.

		Override to establish connections or perform startup work.
		"""
		return None

	async def close(self) -> None:
		"""Async cleanup, called on app shutdown.

		Override to tear down connections or perform cleanup.
		"""
		return None

	@abstractmethod
	async def get(self, sid: str) -> dict[str, Any] | None:
		"""Retrieve session by ID.

		Args:
			sid: Session identifier.

		Returns:
			Session data dict if found, None otherwise.
		"""
		...

	@abstractmethod
	async def create(self, sid: str) -> dict[str, Any]:
		"""Create a new session.

		Args:
			sid: Session identifier.

		Returns:
			New empty session dict.
		"""
		...

	@abstractmethod
	async def delete(self, sid: str) -> None:
		"""Delete a session.

		Args:
			sid: Session identifier.
		"""
		...

	@abstractmethod
	async def save(self, sid: str, session: dict[str, Any]) -> None:
		"""Persist session data.

		Args:
			sid: Session identifier.
			session: Session data to persist.
		"""
		...


class InMemorySessionStore(SessionStore):
	"""In-memory session store implementation.

	Sessions are stored in memory and lost on restart. Suitable for
	development and testing.

	Example:
		```python
		store = ps.InMemorySessionStore()
		app = ps.App(session_store=store)
		```
	"""

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
	async def save(self, sid: str, session: dict[str, Any]) -> None:
		# Should not matter as the session ReactiveDict is normally mutated directly
		self._sessions[sid] = session

	@override
	async def delete(self, sid: str) -> None:
		_ = self._sessions.pop(sid, None)


class SessionCookiePayload(TypedDict):
	sid: str
	data: dict[str, Any]


class CookieSessionStore:
	"""Store sessions in signed cookies. Default session store.

	The cookie stores a compact JSON of the session signed with HMAC-SHA256
	to prevent tampering. Keep session data small (<4KB).

	Args:
		secret: Signing secret. Uses PULSE_SECRET env var if not provided.
			Required in production.
		salt: Salt for HMAC. Default: "pulse.session".
		digestmod: Hash algorithm. Default: "sha256".
		max_cookie_bytes: Maximum cookie size. Default: 3800.

	Environment Variables:
		PULSE_SECRET: Session signing secret (required in production).

	Example:
		```python
		# Uses PULSE_SECRET environment variable
		store = ps.CookieSessionStore()

		# Explicit secret
		store = ps.CookieSessionStore(secret="your-secret-key")

		app = ps.App(session_store=store)
		```
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
		"""Encode session to signed cookie value.

		Args:
			sid: Session identifier.
			session: Session data to encode.

		Returns:
			Signed cookie value string.
		"""
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
		"""Decode and verify signed cookie.

		Args:
			cookie: Signed cookie value string.

		Returns:
			Tuple of (sid, session) if valid, None if invalid or tampered.
		"""
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
