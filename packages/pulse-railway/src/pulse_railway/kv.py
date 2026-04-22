from __future__ import annotations

import abc
import asyncio
import os
import sqlite3
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Literal, override

from pulse_railway.constants import PULSE_KV_PATH, PULSE_KV_URL

try:
	import redis.asyncio as redis
except Exception:
	redis = None


class Store(abc.ABC):
	kind: ClassVar[Literal["memory", "redis", "sqlite"]]

	@property
	def shareable(self) -> bool:
		return False

	@abc.abstractmethod
	async def init(self) -> None: ...

	@abc.abstractmethod
	async def close(self) -> None: ...

	@abc.abstractmethod
	async def get(self, key: str) -> str | None: ...

	@abc.abstractmethod
	async def set(
		self,
		key: str,
		value: str,
		*,
		ttl_seconds: int | None = None,
		only_if_missing: bool = False,
	) -> bool: ...

	@abc.abstractmethod
	async def delete(self, key: str) -> None: ...

	@abc.abstractmethod
	async def scan_prefix(self, prefix: str) -> list[str]: ...


class MemoryStore(Store):
	__slots__: tuple[str, ...] = ("_entries",)
	kind: ClassVar[Literal["memory", "redis", "sqlite"]] = "memory"

	def __init__(self) -> None:
		self._entries: dict[str, tuple[str, float | None]] = {}

	@override
	def __repr__(self) -> str:
		return "MemoryStore()"

	@override
	def __eq__(self, other: object) -> bool:
		return isinstance(other, MemoryStore)

	def _prune(self, key: str | None = None, *, now: float | None = None) -> None:
		timestamp = time.time() if now is None else now
		if key is not None:
			entry = self._entries.get(key)
			if entry is None:
				return
			_, expires_at = entry
			if expires_at is not None and expires_at <= timestamp:
				self._entries.pop(key, None)
			return
		expired = [
			entry_key
			for entry_key, (_, expires_at) in self._entries.items()
			if expires_at is not None and expires_at <= timestamp
		]
		for entry_key in expired:
			self._entries.pop(entry_key, None)

	@override
	async def init(self) -> None:
		return None

	@override
	async def close(self) -> None:
		self._entries.clear()

	@override
	async def get(self, key: str) -> str | None:
		self._prune(key)
		entry = self._entries.get(key)
		if entry is None:
			return None
		return entry[0]

	@override
	async def set(
		self,
		key: str,
		value: str,
		*,
		ttl_seconds: int | None = None,
		only_if_missing: bool = False,
	) -> bool:
		self._prune(key)
		if only_if_missing and key in self._entries:
			return False
		expires_at = None if ttl_seconds is None else time.time() + max(ttl_seconds, 0)
		self._entries[key] = (value, expires_at)
		return True

	@override
	async def delete(self, key: str) -> None:
		self._entries.pop(key, None)

	@override
	async def scan_prefix(self, prefix: str) -> list[str]:
		self._prune()
		return sorted(key for key in self._entries if key.startswith(prefix))


class SQLiteStore(Store):
	__slots__: tuple[str, ...] = ("path", "_lock", "_conn")
	kind: ClassVar[Literal["memory", "redis", "sqlite"]] = "sqlite"

	path: str
	_lock: threading.Lock
	_conn: sqlite3.Connection | None

	def __init__(
		self,
		path: str | os.PathLike[str] | None = None,
		*,
		env: Mapping[str, str] | None = None,
	) -> None:
		if path is None:
			values = os.environ if env is None else env
			path = values.get(PULSE_KV_PATH)
		if path is None:
			raise ValueError(f"SQLiteStore requires path= or {PULSE_KV_PATH}")
		self.path = os.fspath(path)
		self._lock = threading.Lock()
		self._conn = None

	@override
	def __repr__(self) -> str:
		return f"SQLiteStore(path={self.path!r})"

	@override
	def __eq__(self, other: object) -> bool:
		return isinstance(other, SQLiteStore) and self.path == other.path

	def _ensure_conn(self) -> sqlite3.Connection:
		with self._lock:
			if self._conn is None:
				path = Path(self.path)
				path.parent.mkdir(parents=True, exist_ok=True)
				conn = sqlite3.connect(path, check_same_thread=False)
				conn.execute("PRAGMA journal_mode=WAL")
				conn.execute("PRAGMA synchronous=NORMAL")
				conn.execute(
					"""
					CREATE TABLE IF NOT EXISTS pulse_kv (
						key TEXT PRIMARY KEY,
						value TEXT NOT NULL,
						expires_at REAL
					)
					"""
				)
				self._conn = conn
			return self._conn

	def _delete_expired(self, conn: sqlite3.Connection, *, now: float) -> None:
		conn.execute(
			"DELETE FROM pulse_kv WHERE expires_at IS NOT NULL AND expires_at <= ?",
			(now,),
		)
		conn.commit()

	@override
	async def init(self) -> None:
		await asyncio.to_thread(self._ensure_conn)

	@override
	async def close(self) -> None:
		conn = self._conn
		if conn is None:
			return

		def _close() -> None:
			with self._lock:
				if self._conn is not None:
					self._conn.close()
					self._conn = None

		await asyncio.to_thread(_close)

	@override
	async def get(self, key: str) -> str | None:
		def _get() -> str | None:
			now = time.time()
			conn = self._ensure_conn()
			with self._lock:
				self._delete_expired(conn, now=now)
				row = conn.execute(
					"SELECT value FROM pulse_kv WHERE key = ?",
					(key,),
				).fetchone()
				return None if row is None else str(row[0])

		return await asyncio.to_thread(_get)

	@override
	async def set(
		self,
		key: str,
		value: str,
		*,
		ttl_seconds: int | None = None,
		only_if_missing: bool = False,
	) -> bool:
		def _set() -> bool:
			now = time.time()
			expires_at = None if ttl_seconds is None else now + max(ttl_seconds, 0)
			conn = self._ensure_conn()
			with self._lock:
				self._delete_expired(conn, now=now)
				if only_if_missing:
					cursor = conn.execute(
						"INSERT OR IGNORE INTO pulse_kv(key, value, expires_at) VALUES(?, ?, ?)",
						(key, value, expires_at),
					)
					conn.commit()
					return cursor.rowcount > 0
				conn.execute(
					"""
					INSERT INTO pulse_kv(key, value, expires_at)
					VALUES(?, ?, ?)
					ON CONFLICT(key) DO UPDATE SET
						value = excluded.value,
						expires_at = excluded.expires_at
					""",
					(key, value, expires_at),
				)
				conn.commit()
				return True

		return await asyncio.to_thread(_set)

	@override
	async def delete(self, key: str) -> None:
		def _delete() -> None:
			conn = self._ensure_conn()
			with self._lock:
				conn.execute("DELETE FROM pulse_kv WHERE key = ?", (key,))
				conn.commit()

		await asyncio.to_thread(_delete)

	@override
	async def scan_prefix(self, prefix: str) -> list[str]:
		def _scan() -> list[str]:
			now = time.time()
			conn = self._ensure_conn()
			with self._lock:
				self._delete_expired(conn, now=now)
				rows = conn.execute(
					"SELECT key FROM pulse_kv WHERE key LIKE ? ORDER BY key",
					(f"{prefix}%",),
				).fetchall()
				return [str(row[0]) for row in rows]

		return await asyncio.to_thread(_scan)


class RedisStore(Store):
	__slots__: tuple[str, ...] = ("url", "client", "owns_client")
	kind: ClassVar[Literal["memory", "redis", "sqlite"]] = "redis"

	url: str | None
	client: Any
	owns_client: bool

	def __init__(
		self,
		url: str | None = None,
		*,
		env: Mapping[str, str] | None = None,
		client: Any = None,
		owns_client: bool = False,
	) -> None:
		if url is None and client is None:
			values = os.environ if env is None else env
			url = values.get(PULSE_KV_URL)
		if url is None and client is None:
			raise ValueError(f"RedisStore requires url= or {PULSE_KV_URL}")
		self.url = url
		self.client = client
		self.owns_client = owns_client

	@classmethod
	def from_url(cls, url: str) -> RedisStore:
		return cls(url=url)

	@override
	def __repr__(self) -> str:
		return f"RedisStore(url={self.url!r})"

	@override
	def __eq__(self, other: object) -> bool:
		return isinstance(other, RedisStore) and self.url == other.url

	@property
	@override
	def shareable(self) -> bool:
		return True

	def _ensure_client(self) -> Any:
		client = self.client
		if client is not None:
			return client
		if redis is None:
			raise RuntimeError(
				"RedisStore requires the 'redis' package. Install it to use Redis-backed storage."
			)
		if self.url is None:
			raise RuntimeError(f"RedisStore requires url= or {PULSE_KV_URL}")
		client = redis.Redis.from_url(self.url, decode_responses=True)
		self.client = client
		self.owns_client = True
		return client

	@override
	async def init(self) -> None:
		self._ensure_client()

	@override
	async def close(self) -> None:
		if self.owns_client and self.client is not None:
			await self.client.aclose()
			self.client = None

	@override
	async def get(self, key: str) -> str | None:
		value = await self._ensure_client().get(key)
		return None if value is None else str(value)

	@override
	async def set(
		self,
		key: str,
		value: str,
		*,
		ttl_seconds: int | None = None,
		only_if_missing: bool = False,
	) -> bool:
		kwargs: dict[str, object] = {}
		if ttl_seconds is not None:
			kwargs["ex"] = ttl_seconds
		if only_if_missing:
			kwargs["nx"] = True
		result = await self._ensure_client().set(key, value, **kwargs)
		return bool(result) if only_if_missing else True

	@override
	async def delete(self, key: str) -> None:
		await self._ensure_client().delete(key)

	@override
	async def scan_prefix(self, prefix: str) -> list[str]:
		keys: list[str] = []
		async for key in self._ensure_client().scan_iter(match=f"{prefix}*"):
			keys.append(str(key))
		keys.sort()
		return keys


KVStore = Store
MemoryKVStore = MemoryStore
SQLiteKVStore = SQLiteStore
RedisKVStore = RedisStore
InMemoryKVStore = MemoryStore
