from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

try:
	import redis.asyncio as redis
except Exception:
	redis = None


DEFAULT_DEV_KV_PATH = ".pulse/dev.sqlite3"


@dataclass(slots=True)
class KVStoreConfig:
	kind: Literal["redis", "sqlite"]
	url: str | None = None
	path: str | None = None

	@property
	def shareable(self) -> bool:
		return self.kind == "redis"

	def to_env(self) -> dict[str, str]:
		env = {"PULSE_KV_KIND": self.kind}
		if self.url is not None:
			env["PULSE_KV_URL"] = self.url
		if self.path is not None:
			env["PULSE_KV_PATH"] = self.path
		return env


class KVStore(Protocol):
	async def init(self) -> None: ...

	async def close(self) -> None: ...

	async def get(self, key: str) -> str | None: ...

	async def set(
		self,
		key: str,
		value: str,
		*,
		ttl_seconds: int | None = None,
		only_if_missing: bool = False,
	) -> bool: ...

	async def delete(self, key: str) -> None: ...

	async def scan_prefix(self, prefix: str) -> list[str]: ...

	def config(self) -> KVStoreConfig | None: ...


class MemoryKVStore:
	def __init__(self) -> None:
		self._entries: dict[str, tuple[str, float | None]] = {}

	async def init(self) -> None:
		return None

	async def close(self) -> None:
		self._entries.clear()

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

	async def get(self, key: str) -> str | None:
		self._prune(key)
		entry = self._entries.get(key)
		if entry is None:
			return None
		return entry[0]

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

	async def delete(self, key: str) -> None:
		self._entries.pop(key, None)

	async def scan_prefix(self, prefix: str) -> list[str]:
		self._prune()
		return sorted(key for key in self._entries if key.startswith(prefix))

	def config(self) -> KVStoreConfig | None:
		return None


class SQLiteKVStore:
	path: Path
	_lock: threading.Lock
	_conn: sqlite3.Connection | None

	def __init__(self, path: str | Path = DEFAULT_DEV_KV_PATH) -> None:
		self.path = Path(path)
		self._lock = threading.Lock()
		self._conn = None

	def config(self) -> KVStoreConfig | None:
		return KVStoreConfig(kind="sqlite", path=str(self.path))

	def _ensure_conn(self) -> sqlite3.Connection:
		with self._lock:
			if self._conn is None:
				self.path.parent.mkdir(parents=True, exist_ok=True)
				conn = sqlite3.connect(
					self.path,
					check_same_thread=False,
				)
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

	async def init(self) -> None:
		await asyncio.to_thread(self._ensure_conn)

	def _delete_expired(self, conn: sqlite3.Connection, *, now: float) -> None:
		conn.execute(
			"DELETE FROM pulse_kv WHERE expires_at IS NOT NULL AND expires_at <= ?",
			(now,),
		)
		conn.commit()

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

	async def delete(self, key: str) -> None:
		def _delete() -> None:
			conn = self._ensure_conn()
			with self._lock:
				conn.execute("DELETE FROM pulse_kv WHERE key = ?", (key,))
				conn.commit()

		await asyncio.to_thread(_delete)

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


class RedisKVStore:
	client: Any
	url: str | None
	owns_client: bool

	def __init__(
		self,
		*,
		client: Any,
		url: str | None = None,
		owns_client: bool = False,
	) -> None:
		if redis is None:
			raise RuntimeError(
				"RedisKVStore requires the 'redis' package. Install it to use Redis-backed KV storage."
			)
		self.client = client
		self.url = url
		self.owns_client = owns_client

	@classmethod
	def from_url(cls, url: str) -> "RedisKVStore":
		if redis is None:
			raise RuntimeError(
				"RedisKVStore requires the 'redis' package. Install it to use Redis-backed KV storage."
			)
		return cls(
			client=redis.Redis.from_url(url, decode_responses=True),
			url=url,
			owns_client=True,
		)

	async def init(self) -> None:
		return None

	async def close(self) -> None:
		if self.owns_client:
			await self.client.aclose()

	async def get(self, key: str) -> str | None:
		value = await self.client.get(key)
		return None if value is None else str(value)

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
		result = await self.client.set(key, value, **kwargs)
		return bool(result) if only_if_missing else True

	async def delete(self, key: str) -> None:
		await self.client.delete(key)

	async def scan_prefix(self, prefix: str) -> list[str]:
		keys: list[str] = []
		async for key in self.client.scan_iter(match=f"{prefix}*"):
			keys.append(str(key))
		keys.sort()
		return keys

	def config(self) -> KVStoreConfig | None:
		if self.url is None:
			return None
		return KVStoreConfig(kind="redis", url=self.url)


def build_kv_store(config: KVStoreConfig) -> KVStore:
	if config.kind == "redis":
		if config.url is None:
			raise ValueError("Redis KV config requires a url")
		return RedisKVStore.from_url(config.url)
	if config.path is None:
		raise ValueError("SQLite KV config requires a path")
	return SQLiteKVStore(config.path)


InMemoryKVStore = MemoryKVStore


__all__ = [
	"DEFAULT_DEV_KV_PATH",
	"InMemoryKVStore",
	"KVStore",
	"KVStoreConfig",
	"MemoryKVStore",
	"RedisKVStore",
	"SQLiteKVStore",
	"build_kv_store",
]
