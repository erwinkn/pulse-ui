from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, override

from pulse_railway.constants import (
	DEFAULT_REDIS_PREFIX,
	DEPLOYMENT_STATE_PENDING,
	PULSE_KV_KIND,
	PULSE_KV_PATH,
	PULSE_KV_URL,
	REDIS_URL,
)
from pulse_railway.kv import (
	MemoryStore,
	RedisStore,
	SQLiteStore,
	Store,
)


@dataclass(slots=True)
class StoredDeployment:
	deployment_id: str
	state: str | None
	service_name: str | None
	drain_started_at: float | None


class ActiveDeploymentError(RuntimeError):
	def __init__(self, deployment_id: str) -> None:
		super().__init__(f"active deployment cannot be deleted: {deployment_id}")
		self.deployment_id: str = deployment_id


def kv_store_spec_from_env(env: dict[str, str] | None = None) -> Store | None:
	env = env or {}
	kind = env.get(PULSE_KV_KIND) or env.get("kind")
	if kind == "memory":
		return MemoryStore()
	if kind == "redis":
		url = env.get(PULSE_KV_URL) or env.get(REDIS_URL) or env.get("url")
		if url is None:
			return None
		return RedisStore(url=url)
	if kind == "sqlite":
		path = env.get(PULSE_KV_PATH) or env.get("path")
		if path is None:
			return None
		return SQLiteStore(path=path)
	redis_url = env.get(PULSE_KV_URL) or env.get(REDIS_URL)
	if redis_url is not None:
		return RedisStore(url=redis_url)
	return None


class DeploymentStore:
	def __init__(
		self,
		store: Store,
		prefix: str = DEFAULT_REDIS_PREFIX,
		owns_store: bool = False,
	) -> None:
		self.store: Store = store
		self.prefix: str = prefix.rstrip(":")
		self.owns_store: bool = owns_store

	def _deployment_prefix(self) -> str:
		return f"{self.prefix}:deployment:"

	def _deployment_key(self, deployment_id: str) -> str:
		return f"{self._deployment_prefix()}{deployment_id}"

	def _lock_key(self) -> str:
		return f"{self.prefix}:janitor:lock"

	def _active_key(self) -> str:
		return f"{self.prefix}:active"

	async def close(self) -> None:
		if self.owns_store:
			await self.store.close()

	async def get_deployment(self, deployment_id: str) -> StoredDeployment | None:
		payload = await self.store.get(self._deployment_key(deployment_id))
		if payload is None:
			return None
		record = json.loads(payload)
		return StoredDeployment(
			deployment_id=deployment_id,
			state=record.get("state"),
			service_name=record.get("service_name"),
			drain_started_at=_to_float(record.get("drain_started_at")),
		)

	async def save_deployment(self, deployment: StoredDeployment) -> None:
		payload = json.dumps(asdict(deployment), separators=(",", ":"))
		await self.store.set(self._deployment_key(deployment.deployment_id), payload)

	async def set_active(
		self,
		*,
		deployment_id: str,
		service_name: str,
	) -> None:
		await self.store.set(self._active_key(), deployment_id)
		await self.save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state="active",
				service_name=service_name,
				drain_started_at=None,
			)
		)

	async def register_deployment(
		self,
		*,
		deployment_id: str,
		service_name: str,
	) -> None:
		await self.save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state=DEPLOYMENT_STATE_PENDING,
				service_name=service_name,
				drain_started_at=None,
			)
		)

	async def get_active_deployment(self) -> str | None:
		return await self.store.get(self._active_key())

	async def mark_draining(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		current = await self.get_deployment(deployment_id)
		if current is None:
			current = StoredDeployment(
				deployment_id=deployment_id,
				state=None,
				service_name=service_name,
				drain_started_at=None,
			)
		await self.save_deployment(
			StoredDeployment(
				deployment_id=deployment_id,
				state="draining",
				service_name=service_name or current.service_name,
				drain_started_at=current.drain_started_at or timestamp,
			)
		)

	async def list_draining_deployments(self) -> list[StoredDeployment]:
		deployment_keys = await self.store.scan_prefix(self._deployment_prefix())
		draining: list[StoredDeployment] = []
		for key in deployment_keys:
			deployment_id = key.removeprefix(self._deployment_prefix())
			record = await self.get_deployment(deployment_id)
			if record is not None and record.state == "draining":
				draining.append(record)
		return draining

	async def delete_inactive_deployment(self, *, deployment_id: str) -> None:
		if await self.get_active_deployment() == deployment_id:
			raise ActiveDeploymentError(deployment_id)

		await self.store.delete(self._deployment_key(deployment_id))

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
	) -> None:
		super().__init__(
			store=MemoryStore(),
			prefix=prefix,
			owns_store=False,
		)

	@override
	async def close(self) -> None:
		return None


class SQLiteDeploymentStore(DeploymentStore):
	def __init__(
		self,
		*,
		path: str | Path,
		prefix: str = DEFAULT_REDIS_PREFIX,
	) -> None:
		super().__init__(
			store=SQLiteStore(path),
			prefix=prefix,
			owns_store=True,
		)


class RedisDeploymentStore(DeploymentStore):
	def __init__(
		self,
		*,
		client: object | None = None,
		store: RedisStore | None = None,
		prefix: str = DEFAULT_REDIS_PREFIX,
		owns_client: bool = False,
	) -> None:
		if store is None:
			if client is None:
				raise RuntimeError(
					"RedisDeploymentStore requires a Redis client or store."
				)
			store = RedisStore(client=client, owns_client=owns_client)
		self.client: Any = store.client
		super().__init__(
			store=store,
			prefix=prefix,
			owns_store=True,
		)

	@classmethod
	def from_url(
		cls,
		*,
		url: str,
		prefix: str = DEFAULT_REDIS_PREFIX,
	) -> RedisDeploymentStore:
		return cls(
			store=RedisStore.from_url(url),
			prefix=prefix,
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
	"ActiveDeploymentError",
	"DeploymentStore",
	"Store",
	"MemoryStore",
	"RedisStore",
	"SQLiteStore",
	"MemoryDeploymentStore",
	"RedisDeploymentStore",
	"StoredDeployment",
	"SQLiteDeploymentStore",
	"kv_store_spec_from_env",
]
