from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pulse.kv import (
	KVStore,
	KVStoreConfig,
	MemoryKVStore,
	RedisKVStore,
	SQLiteKVStore,
)

from pulse_railway.constants import (
	DEFAULT_REDIS_PREFIX,
	DEFAULT_WEBSOCKET_TTL_SECONDS,
	PULSE_KV_KIND,
	PULSE_KV_PATH,
	PULSE_KV_URL,
	PULSE_REDIS_URL,
)

InMemoryKVStore = MemoryKVStore
KVStoreSpec = KVStoreConfig


@dataclass(slots=True)
class StoredDeployment:
	deployment_id: str
	state: str | None
	service_name: str | None
	last_seen_at: float | None
	drain_started_at: float | None


def kv_store_spec_from_env(
	env: dict[str, str] | None = None,
) -> KVStoreConfig | None:
	source = env or {}
	kind = source.get(PULSE_KV_KIND) or source.get("kind")
	if kind == "redis":
		url = (
			source.get(PULSE_KV_URL) or source.get(PULSE_REDIS_URL) or source.get("url")
		)
		if url is None:
			return None
		return KVStoreConfig(kind="redis", url=url)
	if kind == "sqlite":
		path = source.get(PULSE_KV_PATH) or source.get("path")
		if path is None:
			return None
		return KVStoreConfig(kind="sqlite", path=path)
	redis_url = source.get(PULSE_KV_URL) or source.get(PULSE_REDIS_URL)
	if redis_url is not None:
		return KVStoreConfig(kind="redis", url=redis_url)
	return None


class DeploymentStore:
	def __init__(
		self,
		store: KVStore,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
		owns_store: bool = False,
	) -> None:
		self.store = store
		self.prefix = prefix.rstrip(":")
		self.websocket_ttl_seconds = websocket_ttl_seconds
		self.owns_store = owns_store

	def _deployment_prefix(self) -> str:
		return f"{self.prefix}:deployment:"

	def _deployment_key(self, deployment_id: str) -> str:
		return f"{self._deployment_prefix()}{deployment_id}"

	def _websocket_prefix(self, deployment_id: str) -> str:
		return f"{self._deployment_key(deployment_id)}:ws:"

	def _websocket_key(self, deployment_id: str, lease_id: str) -> str:
		return f"{self._websocket_prefix(deployment_id)}{lease_id}"

	def _lock_key(self) -> str:
		return f"{self.prefix}:janitor:lock"

	async def close(self) -> None:
		if self.owns_store:
			await self.store.close()

	async def _get_deployment(self, deployment_id: str) -> StoredDeployment | None:
		payload = await self.store.get(self._deployment_key(deployment_id))
		if payload is None:
			return None
		record = json.loads(payload)
		return StoredDeployment(
			deployment_id=deployment_id,
			state=record.get("state"),
			service_name=record.get("service_name"),
			last_seen_at=_to_float(record.get("last_seen_at")),
			drain_started_at=_to_float(record.get("drain_started_at")),
		)

	async def _save_deployment(self, deployment: StoredDeployment) -> None:
		payload = json.dumps(asdict(deployment), separators=(",", ":"))
		await self.store.set(self._deployment_key(deployment.deployment_id), payload)

	async def mark_active(
		self,
		*,
		deployment_id: str,
		service_name: str,
		now: float | None = None,
	) -> None:
		await self._save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state="active",
				service_name=service_name,
				last_seen_at=_now(now),
				drain_started_at=None,
			)
		)

	async def mark_draining(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		current = await self._get_deployment(deployment_id)
		if current is None:
			current = StoredDeployment(
				deployment_id=deployment_id,
				state=None,
				service_name=service_name,
				last_seen_at=None,
				drain_started_at=None,
			)
		await self._save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state="draining",
				service_name=service_name or current.service_name,
				last_seen_at=current.last_seen_at,
				drain_started_at=current.drain_started_at or timestamp,
			)
		)

	async def record_request(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		current = await self._get_deployment(deployment_id)
		if current is None:
			current = StoredDeployment(
				deployment_id=deployment_id,
				state="active",
				service_name=service_name,
				last_seen_at=None,
				drain_started_at=None,
			)
		await self._save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state=current.state or "active",
				service_name=service_name or current.service_name,
				last_seen_at=timestamp,
				drain_started_at=current.drain_started_at,
			)
		)

	async def create_websocket_lease(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> str:
		lease_id = secrets.token_hex(8)
		await self.refresh_websocket_lease(
			deployment_id=deployment_id,
			lease_id=lease_id,
			now=now,
		)
		if service_name:
			await self.record_request(
				deployment_id=deployment_id,
				service_name=service_name,
				now=now,
			)
		return lease_id

	async def refresh_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None:
		timestamp = str(_now(now))
		await self.store.set(
			self._websocket_key(deployment_id, lease_id),
			timestamp,
			ttl_seconds=self.websocket_ttl_seconds,
		)
		await self.record_request(deployment_id=deployment_id, now=_to_float(timestamp))

	async def remove_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None:
		await self.store.delete(self._websocket_key(deployment_id, lease_id))
		await self.record_request(deployment_id=deployment_id, now=now)

	async def count_websocket_leases(self, *, deployment_id: str) -> int:
		return len(await self.store.scan_prefix(self._websocket_prefix(deployment_id)))

	async def list_draining_deployments(self) -> list[StoredDeployment]:
		deployment_keys = await self.store.scan_prefix(self._deployment_prefix())
		draining: list[StoredDeployment] = []
		for key in deployment_keys:
			if ":ws:" in key:
				continue
			deployment_id = key.removeprefix(self._deployment_prefix())
			record = await self._get_deployment(deployment_id)
			if record is not None and record.state == "draining":
				draining.append(record)
		return draining

	async def clear_deployment(self, *, deployment_id: str) -> None:
		await self.store.delete(self._deployment_key(deployment_id))
		for key in await self.store.scan_prefix(self._websocket_prefix(deployment_id)):
			await self.store.delete(key)

	async def acquire_janitor_lock(self, *, token: str, ttl_seconds: int) -> bool:
		return await self.store.set(
			self._lock_key(),
			token,
			ttl_seconds=ttl_seconds,
			only_if_missing=True,
		)

	async def release_janitor_lock(self, *, token: str) -> None:
		value = await self.store.get(self._lock_key())
		if value == token:
			await self.store.delete(self._lock_key())


class MemoryDeploymentStore(DeploymentStore):
	def __init__(
		self,
		*,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
	) -> None:
		super().__init__(
			store=MemoryKVStore(),
			prefix=prefix,
			websocket_ttl_seconds=websocket_ttl_seconds,
			owns_store=False,
		)

	async def close(self) -> None:
		return None


class SQLiteDeploymentStore(DeploymentStore):
	def __init__(
		self,
		*,
		path: str | Path,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
	) -> None:
		super().__init__(
			store=SQLiteKVStore(path),
			prefix=prefix,
			websocket_ttl_seconds=websocket_ttl_seconds,
			owns_store=True,
		)


class RedisDeploymentStore(DeploymentStore):
	def __init__(
		self,
		*,
		client: object | None = None,
		store: RedisKVStore | None = None,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
		owns_client: bool = False,
	) -> None:
		if store is None:
			if client is None:
				raise RuntimeError(
					"RedisDeploymentStore requires a Redis client or store."
				)
			store = RedisKVStore(client=client, owns_client=owns_client)
		self.client = store.client
		super().__init__(
			store=store,
			prefix=prefix,
			websocket_ttl_seconds=websocket_ttl_seconds,
			owns_store=True,
		)

	@classmethod
	def from_url(
		cls,
		*,
		url: str,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
	) -> RedisDeploymentStore:
		return cls(
			store=RedisKVStore.from_url(url),
			prefix=prefix,
			websocket_ttl_seconds=websocket_ttl_seconds,
		)


def _to_float(value: str | float | None) -> float | None:
	if value is None:
		return None
	if isinstance(value, float):
		return value
	return float(value)


def _now(value: float | None) -> float:
	return time.time() if value is None else value


__all__ = [
	"DeploymentStore",
	"InMemoryKVStore",
	"KVStoreSpec",
	"MemoryDeploymentStore",
	"RedisDeploymentStore",
	"SQLiteDeploymentStore",
	"StoredDeployment",
	"kv_store_spec_from_env",
]
