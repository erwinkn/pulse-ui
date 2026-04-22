from __future__ import annotations


class FakeRedisClient:
	def __init__(self) -> None:
		self.data: dict[str, str] = {}
		self.closed = False

	async def get(self, key: str) -> str | None:
		return self.data.get(key)

	async def set(self, key: str, value: str) -> bool:
		self.data[key] = value
		return True

	async def delete(self, key: str) -> None:
		self.data.pop(key, None)

	async def aclose(self) -> None:
		self.closed = True
