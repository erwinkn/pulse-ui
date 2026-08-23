"""Single request/reply primitive for server-initiated exchanges.

`call_api`, `run_js`, and `Channel.request` all follow the same protocol:
mint a correlation id, park a future here, send a typed command to the
client, and await the future. The matching `{type: "reply", id}` packet
resolves it synchronously — no middleware, no awaits between packet and
`set_result`.

Command payloads stay at the call sites (`api_call`, `js_exec`,
`channel_message`). Unknown or already-resolved ids are ignored: a reply
can race a timeout or a channel close, and the loser must be a no-op.
"""

import asyncio
from typing import Any

from pulse.messages import ReplyMessage


class PendingReplies:
	"""Correlation id -> future. Resolution never awaits."""

	_futures: dict[str, asyncio.Future[Any]]
	_cancel_keys: dict[str, str]

	def __init__(self) -> None:
		self._futures = {}
		self._cancel_keys = {}

	def __len__(self) -> int:
		return len(self._futures)

	def __contains__(self, reply_id: str) -> bool:
		return reply_id in self._futures

	def register(
		self,
		reply_id: str,
		*,
		cancel_key: str | None = None,
	) -> asyncio.Future[Any]:
		"""Create and park a future until the client reply for `reply_id` arrives.

		`cancel_key` groups requests that die together (e.g. all inflight
		requests of one channel), failed via `reject_where`.
		"""
		if reply_id in self._futures:
			raise ValueError(f"Duplicate pending reply id {reply_id!r}")
		future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
		self._futures[reply_id] = future
		if cancel_key is not None:
			self._cancel_keys[reply_id] = cancel_key
		return future

	def apply(self, message: ReplyMessage) -> None:
		"""Resolve or reject from a `reply` packet. Missing ids are no-ops."""
		reply_id = message["id"]
		error = message.get("error")
		if error is not None:
			self.reject(
				reply_id,
				error if isinstance(error, BaseException) else RuntimeError(str(error)),
			)
		else:
			self.resolve(reply_id, message.get("payload"))

	def resolve(self, reply_id: str, value: Any) -> None:
		future = self._pop(reply_id)
		if future is not None and not future.done():
			future.set_result(value)

	def reject(self, reply_id: str, error: BaseException) -> None:
		future = self._pop(reply_id)
		if future is not None and not future.done():
			future.set_exception(error)

	def discard(self, reply_id: str) -> None:
		"""Forget a pending reply without touching its future (timeouts)."""
		self._pop(reply_id)

	def reject_where(self, cancel_key: str, error: BaseException) -> None:
		reply_ids = [
			reply_id for reply_id, key in self._cancel_keys.items() if key == cancel_key
		]
		for reply_id in reply_ids:
			self.reject(reply_id, error)

	def cancel_all(self) -> None:
		for future in self._futures.values():
			if not future.done():
				future.cancel()
		self._futures.clear()
		self._cancel_keys.clear()

	def _pop(self, reply_id: str) -> asyncio.Future[Any] | None:
		self._cancel_keys.pop(reply_id, None)
		return self._futures.pop(reply_id, None)
