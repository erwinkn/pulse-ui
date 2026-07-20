import base64
import hmac
import json
import math
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


def encode_session_json(session: object) -> str:
	"""Encode persistent session data without lossy Python-to-JSON coercions."""
	if type(session) is not dict:
		raise TypeError("Session data must be a JSON object")
	_validate_session_value(cast(object, session), "$", set())
	return json.dumps(session, separators=(",", ":"), allow_nan=False)


def decode_session_json(payload: str) -> dict[str, Any]:
	"""Decode and validate a persistent JSON session object."""
	value: object = json.loads(
		payload,
		parse_float=_parse_session_float,
		parse_constant=_reject_session_constant,
	)
	if type(value) is not dict:
		raise TypeError("Session data must be a JSON object")
	_validate_session_value(cast(object, value), "$", set())
	return cast(dict[str, Any], value)


def _validate_session_value(value: object, path: str, active: set[int]) -> None:
	value_type = type(value)
	if value is None or value_type in {bool, int, str}:
		return
	if value_type is float:
		if not math.isfinite(cast(float, value)):
			raise TypeError(f"Session data at {path} must contain a finite number")
		return
	if value_type not in {list, dict}:
		raise TypeError(
			f"Session data at {path} must contain only JSON-compatible values, "
			+ f"got {value_type.__name__}"
		)

	identity = id(value)
	if identity in active:
		raise TypeError(f"Session data at {path} cannot contain a cycle")
	active.add(identity)
	try:
		if value_type is list:
			for index, entry in enumerate(cast(list[object], value)):
				_validate_session_value(entry, f"{path}[{index}]", active)
			return
		for key, entry in cast(dict[object, object], value).items():
			if type(key) is not str:
				raise TypeError(f"Session data at {path} must use string object keys")
			_validate_session_value(entry, f"{path}.{key}", active)
	finally:
		active.remove(identity)


def _parse_session_float(value: str) -> float:
	parsed = float(value)
	if not math.isfinite(parsed):
		raise ValueError("Session JSON numbers must be finite")
	return parsed


def _reject_session_constant(value: str) -> None:
	raise ValueError(f"Session JSON cannot contain {value}")


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

	async def handle_response(self, res: Response):
		# For cookie sessions, run the effect now if it's scheduled, in order to set the updated cookie
		if self.is_cookie_session:
			self._effect.flush()
		else:
			assert isinstance(self._effect, AsyncEffect)
			if self._effect.is_scheduled:
				await self._effect.wait()
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
	to prevent tampering. Session values must be JSON-compatible and remain under
	the configured cookie-size limit.

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
		data = SessionCookiePayload(sid=sid, data=dict(session))
		payload_json = encode_session_json(data).encode("utf-8")
		compressed = zlib.compress(payload_json, level=6)
		signed = self._sign(compressed)
		if len(signed) > self.max_cookie_bytes:
			raise ValueError(
				f"Session cookie is too large: {len(signed)} bytes exceeds "
				+ f"the {self.max_cookie_bytes}-byte limit"
			)
		return signed

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
			data = decode_session_json(payload_json)
			sid = data.get("sid")
			session = data.get("data")
			if type(sid) is not str or type(session) is not dict:
				return None
			return sid, ReactiveDict(cast(dict[str, Any], session))
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
