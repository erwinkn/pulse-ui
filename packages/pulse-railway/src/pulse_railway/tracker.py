from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from pulse_railway.constants import DEFAULT_REDIS_PREFIX, DEFAULT_WEBSOCKET_TTL_SECONDS

try:
	import redis.asyncio as redis
except Exception:
	redis = None


@dataclass(slots=True)
class TrackedDeployment:
	deployment_id: str
	state: str | None
	service_name: str | None
	last_seen_at: float | None
	drain_started_at: float | None


class DeploymentTracker(Protocol):
	async def close(self) -> None: ...

	async def mark_active(
		self,
		*,
		deployment_id: str,
		service_name: str,
		now: float | None = None,
	) -> None: ...

	async def mark_draining(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None: ...

	async def record_request(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None: ...

	async def create_websocket_lease(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> str: ...

	async def refresh_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None: ...

	async def remove_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None: ...

	async def count_websocket_leases(self, *, deployment_id: str) -> int: ...

	async def list_draining_deployments(self) -> list[TrackedDeployment]: ...

	async def clear_deployment(self, *, deployment_id: str) -> None: ...

	async def acquire_janitor_lock(self, *, token: str, ttl_seconds: int) -> bool: ...

	async def release_janitor_lock(self, *, token: str) -> None: ...


class MemoryDeploymentTracker:
	def __init__(self) -> None:
		self._deployments: dict[str, TrackedDeployment] = {}
		self._leases: dict[str, dict[str, float]] = {}
		self._lock_token: str | None = None

	async def close(self) -> None:
		return None

	async def mark_active(
		self,
		*,
		deployment_id: str,
		service_name: str,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		self._deployments[deployment_id] = TrackedDeployment(
			deployment_id=deployment_id,
			state="active",
			service_name=service_name,
			last_seen_at=timestamp,
			drain_started_at=None,
		)

	async def mark_draining(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		current = self._deployments.get(
			deployment_id,
			TrackedDeployment(
				deployment_id=deployment_id,
				state=None,
				service_name=service_name,
				last_seen_at=None,
				drain_started_at=None,
			),
		)
		self._deployments[deployment_id] = TrackedDeployment(
			deployment_id=deployment_id,
			state="draining",
			service_name=service_name or current.service_name,
			last_seen_at=current.last_seen_at,
			drain_started_at=current.drain_started_at or timestamp,
		)

	async def record_request(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = _now(now)
		current = self._deployments.get(
			deployment_id,
			TrackedDeployment(
				deployment_id=deployment_id,
				state="active",
				service_name=service_name,
				last_seen_at=None,
				drain_started_at=None,
			),
		)
		self._deployments[deployment_id] = TrackedDeployment(
			deployment_id=deployment_id,
			state=current.state or "active",
			service_name=service_name or current.service_name,
			last_seen_at=timestamp,
			drain_started_at=current.drain_started_at,
		)

	async def create_websocket_lease(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> str:
		lease_id = secrets.token_hex(8)
		await self.record_request(
			deployment_id=deployment_id, service_name=service_name, now=now
		)
		self._leases.setdefault(deployment_id, {})[lease_id] = _now(now)
		return lease_id

	async def refresh_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None:
		if (
			deployment_id not in self._leases
			or lease_id not in self._leases[deployment_id]
		):
			return
		timestamp = _now(now)
		self._leases[deployment_id][lease_id] = timestamp
		await self.record_request(deployment_id=deployment_id, now=timestamp)

	async def remove_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None:
		if deployment_id in self._leases:
			self._leases[deployment_id].pop(lease_id, None)
			if not self._leases[deployment_id]:
				self._leases.pop(deployment_id, None)
		await self.record_request(deployment_id=deployment_id, now=now)

	async def count_websocket_leases(self, *, deployment_id: str) -> int:
		return len(self._leases.get(deployment_id, {}))

	async def list_draining_deployments(self) -> list[TrackedDeployment]:
		return [
			deployment
			for deployment in self._deployments.values()
			if deployment.state == "draining"
		]

	async def clear_deployment(self, *, deployment_id: str) -> None:
		self._deployments.pop(deployment_id, None)
		self._leases.pop(deployment_id, None)

	async def acquire_janitor_lock(self, *, token: str, ttl_seconds: int) -> bool:
		_ = ttl_seconds
		if self._lock_token is not None:
			return False
		self._lock_token = token
		return True

	async def release_janitor_lock(self, *, token: str) -> None:
		if self._lock_token == token:
			self._lock_token = None


class RedisDeploymentTracker:
	def __init__(
		self,
		*,
		client: "redis.Redis",
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
		owns_client: bool = False,
	) -> None:
		if redis is None:
			raise RuntimeError(
				"RedisDeploymentTracker requires the 'redis' package. Install it to enable the janitor."
			)
		self.client = client
		self.prefix = prefix.rstrip(":")
		self.websocket_ttl_seconds = websocket_ttl_seconds
		self.owns_client = owns_client

	@classmethod
	def from_url(
		cls,
		*,
		url: str,
		prefix: str = DEFAULT_REDIS_PREFIX,
		websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS,
	) -> "RedisDeploymentTracker":
		if redis is None:
			raise RuntimeError(
				"RedisDeploymentTracker requires the 'redis' package. Install it to enable the janitor."
			)
		client = redis.Redis.from_url(url, decode_responses=True)
		return cls(
			client=client,
			prefix=prefix,
			websocket_ttl_seconds=websocket_ttl_seconds,
			owns_client=True,
		)

	def _deployments_key(self) -> str:
		return f"{self.prefix}:deployments"

	def _deployment_key(self, deployment_id: str) -> str:
		return f"{self.prefix}:deployment:{deployment_id}"

	def _websocket_key(self, deployment_id: str, lease_id: str) -> str:
		return f"{self.prefix}:deployment:{deployment_id}:ws:{lease_id}"

	def _websocket_pattern(self, deployment_id: str) -> str:
		return f"{self.prefix}:deployment:{deployment_id}:ws:*"

	def _lock_key(self) -> str:
		return f"{self.prefix}:janitor:lock"

	async def close(self) -> None:
		if self.owns_client:
			await self.client.aclose()

	async def mark_active(
		self,
		*,
		deployment_id: str,
		service_name: str,
		now: float | None = None,
	) -> None:
		timestamp = str(_now(now))
		key = self._deployment_key(deployment_id)
		pipe = self.client.pipeline()
		pipe.sadd(self._deployments_key(), deployment_id)
		pipe.hset(
			key,
			mapping={
				"state": "active",
				"service_name": service_name,
				"last_seen_at": timestamp,
			},
		)
		pipe.hdel(key, "drain_started_at")
		await pipe.execute()

	async def mark_draining(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = str(_now(now))
		key = self._deployment_key(deployment_id)
		current_state = await self.client.hget(key, "state")
		pipe = self.client.pipeline()
		pipe.sadd(self._deployments_key(), deployment_id)
		mapping: dict[str, str] = {"state": "draining"}
		if service_name:
			mapping["service_name"] = service_name
		pipe.hset(key, mapping=mapping)
		if current_state != "draining":
			pipe.hset(key, mapping={"drain_started_at": timestamp})
		await pipe.execute()

	async def record_request(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> None:
		timestamp = str(_now(now))
		key = self._deployment_key(deployment_id)
		mapping: dict[str, str] = {"last_seen_at": timestamp}
		if service_name:
			mapping["service_name"] = service_name
		pipe = self.client.pipeline()
		pipe.sadd(self._deployments_key(), deployment_id)
		pipe.hset(key, mapping=mapping)
		await pipe.execute()

	async def create_websocket_lease(
		self,
		*,
		deployment_id: str,
		service_name: str | None = None,
		now: float | None = None,
	) -> str:
		lease_id = secrets.token_hex(8)
		await self.refresh_websocket_lease(
			deployment_id=deployment_id, lease_id=lease_id, now=now
		)
		if service_name:
			await self.record_request(
				deployment_id=deployment_id, service_name=service_name, now=now
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
		pipe = self.client.pipeline()
		pipe.set(
			self._websocket_key(deployment_id, lease_id),
			timestamp,
			ex=self.websocket_ttl_seconds,
		)
		pipe.sadd(self._deployments_key(), deployment_id)
		pipe.hset(
			self._deployment_key(deployment_id),
			mapping={"last_seen_at": timestamp},
		)
		await pipe.execute()

	async def remove_websocket_lease(
		self,
		*,
		deployment_id: str,
		lease_id: str,
		now: float | None = None,
	) -> None:
		pipe = self.client.pipeline()
		pipe.delete(self._websocket_key(deployment_id, lease_id))
		pipe.hset(
			self._deployment_key(deployment_id),
			mapping={"last_seen_at": str(_now(now))},
		)
		await pipe.execute()

	async def count_websocket_leases(self, *, deployment_id: str) -> int:
		count = 0
		async for _ in self.client.scan_iter(
			match=self._websocket_pattern(deployment_id)
		):
			count += 1
		return count

	async def list_draining_deployments(self) -> list[TrackedDeployment]:
		deployments: list[TrackedDeployment] = []
		for deployment_id in await self.client.smembers(self._deployments_key()):
			record = await self.client.hgetall(self._deployment_key(deployment_id))
			if record.get("state") != "draining":
				continue
			deployments.append(
				TrackedDeployment(
					deployment_id=deployment_id,
					state=record.get("state"),
					service_name=record.get("service_name"),
					last_seen_at=_to_float(record.get("last_seen_at")),
					drain_started_at=_to_float(record.get("drain_started_at")),
				)
			)
		return deployments

	async def clear_deployment(self, *, deployment_id: str) -> None:
		pipe = self.client.pipeline()
		pipe.srem(self._deployments_key(), deployment_id)
		pipe.delete(self._deployment_key(deployment_id))
		async for key in self.client.scan_iter(
			match=self._websocket_pattern(deployment_id)
		):
			pipe.delete(key)
		await pipe.execute()

	async def acquire_janitor_lock(self, *, token: str, ttl_seconds: int) -> bool:
		acquired = await self.client.set(
			self._lock_key(),
			token,
			ex=ttl_seconds,
			nx=True,
		)
		return bool(acquired)

	async def release_janitor_lock(self, *, token: str) -> None:
		value = await self.client.get(self._lock_key())
		if value == token:
			await self.client.delete(self._lock_key())


def _to_float(value: str | None) -> float | None:
	if value is None:
		return None
	return float(value)


def _now(value: float | None) -> float:
	return time.time() if value is None else value


__all__ = [
	"DeploymentTracker",
	"MemoryDeploymentTracker",
	"RedisDeploymentTracker",
	"TrackedDeployment",
]
