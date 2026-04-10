from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, cast, override

import pulse as ps
from pulse.serializer import Serialized, deserialize, serialize

from pulse_railway.constants import PULSE_REDIS_URL

try:
	import redis.asyncio as redis
except Exception:
	redis = None


class RailwayRedisSessionStore(ps.SessionStore):
	url: str | None
	client: Any
	owns_client: bool
	prefix: str
	fallback: ps.SessionStore | None
	_env: Mapping[str, str] | None

	def __init__(
		self,
		url: str | None = None,
		*,
		env: Mapping[str, str] | None = None,
		client: Any = None,
		owns_client: bool = False,
		prefix: str = "pulse:session",
		fallback: ps.SessionStore | None = None,
	) -> None:
		self.url = url
		self.client = client
		self.owns_client = owns_client
		self.prefix = prefix.rstrip(":")
		self.fallback = fallback
		self._env = env

	@classmethod
	def from_url(
		cls,
		url: str,
		*,
		prefix: str = "pulse:session",
		fallback: ps.SessionStore | None = None,
	) -> RailwayRedisSessionStore:
		return cls(url=url, prefix=prefix, fallback=fallback)

	@override
	def __repr__(self) -> str:
		return (
			"RailwayRedisSessionStore("
			f"url={self.url!r}, prefix={self.prefix!r}, fallback={self.fallback!r})"
		)

	@override
	def __eq__(self, other: object) -> bool:
		return (
			isinstance(other, RailwayRedisSessionStore)
			and self.url == other.url
			and self.prefix == other.prefix
			and type(self.fallback) is type(other.fallback)
		)

	def configured_url(self) -> str | None:
		if self.url is not None:
			return self.url
		values = os.environ if self._env is None else self._env
		return values.get(PULSE_REDIS_URL)

	def current_store(self) -> ps.SessionStore:
		if self._use_fallback():
			assert self.fallback is not None
			return self.fallback
		return self

	def _key(self, sid: str) -> str:
		return f"{self.prefix}:{sid}"

	def _use_fallback(self) -> bool:
		return (
			self.configured_url() is None
			and self.client is None
			and self.fallback is not None
		)

	def _ensure_client(self) -> Any:
		client = self.client
		if client is not None:
			return client
		if redis is None:
			raise RuntimeError(
				"RailwayRedisSessionStore requires the 'redis' package. Install it to use Redis-backed sessions."
			)
		url = self.configured_url()
		if url is None:
			raise RuntimeError(
				f"RailwayRedisSessionStore requires url= or {PULSE_REDIS_URL}"
			)
		client = redis.Redis.from_url(url, decode_responses=True)
		self.client = client
		self.owns_client = True
		return client

	@override
	async def init(self) -> None:
		if self._use_fallback():
			assert self.fallback is not None
			await self.fallback.init()
			return
		self._ensure_client()

	@override
	async def close(self) -> None:
		if self._use_fallback():
			assert self.fallback is not None
			await self.fallback.close()
			return
		if self.owns_client and self.client is not None:
			await self.client.aclose()
			self.client = None

	@override
	async def get(self, sid: str) -> dict[str, Any] | None:
		if self._use_fallback():
			assert self.fallback is not None
			return await self.fallback.get(sid)
		payload = await self._ensure_client().get(self._key(sid))
		if payload is None:
			return None
		return cast(
			dict[str, Any],
			deserialize(cast(Serialized, json.loads(payload))),
		)

	@override
	async def create(self, sid: str) -> dict[str, Any]:
		if self._use_fallback():
			assert self.fallback is not None
			return await self.fallback.create(sid)
		session: dict[str, Any] = {}
		await self.save(sid, session)
		return session

	@override
	async def delete(self, sid: str) -> None:
		if self._use_fallback():
			assert self.fallback is not None
			await self.fallback.delete(sid)
			return
		await self._ensure_client().delete(self._key(sid))

	@override
	async def save(self, sid: str, session: dict[str, Any]) -> None:
		if self._use_fallback():
			assert self.fallback is not None
			await self.fallback.save(sid, session)
			return
		payload = json.dumps(
			serialize(dict(session)),
			separators=(",", ":"),
		)
		await self._ensure_client().set(self._key(sid), payload)


def redis_session_store(
	url: str | None = None,
	*,
	env: Mapping[str, str] | None = None,
	client: Any = None,
	owns_client: bool = False,
	prefix: str = "pulse:session",
	fallback: ps.SessionStore | None = None,
) -> RailwayRedisSessionStore:
	return RailwayRedisSessionStore(
		url=url,
		env=env,
		client=client,
		owns_client=owns_client,
		prefix=prefix,
		fallback=fallback,
	)


RailwaySessionStore = RailwayRedisSessionStore
RedisSessionStore = RailwayRedisSessionStore


def railway_session_store(
	url: str | None = None,
	*,
	env: Mapping[str, str] | None = None,
	client: Any = None,
	owns_client: bool = False,
	prefix: str = "pulse:session",
	fallback: ps.SessionStore | None = None,
) -> RailwayRedisSessionStore:
	return redis_session_store(
		url=url,
		env=env,
		client=client,
		owns_client=owns_client,
		prefix=prefix,
		fallback=fallback,
	)


__all__ = [
	"RailwayRedisSessionStore",
	"RailwaySessionStore",
	"RedisSessionStore",
	"redis_session_store",
	"railway_session_store",
]
