"""Single request/reply primitive for server-initiated exchanges.

`call_api`, `eval_js`, and `Channel.request` all follow the same protocol:
mint a correlation id, park a future here, send a typed command to the
client, and await the future. The matching `{type: "reply", id}` packet
resolves it synchronously — no middleware, no awaits between packet and
`set_result`.

Command payloads stay at the call sites (`api_call`, `js_exec`,
`channel_message`). Unknown or already-resolved ids are ignored: a reply
can race a timeout or a channel close, and the loser must be a no-op.
"""

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from pulse.messages import ReplyMessage


@dataclass(slots=True)
class _Pending:
	future: asyncio.Future[Any]
	cancel_key: str | None
	error: type[BaseException]


@dataclass(slots=True)
class PendingReply:
	id: str
	future: asyncio.Future[Any]


class PendingReplies:
	"""Correlation id -> pending future and request metadata."""

	_pending: dict[str, _Pending]

	def __init__(self) -> None:
		self._pending = {}

	def __len__(self) -> int:
		return len(self._pending)

	def __contains__(self, reply_id: str) -> bool:
		return reply_id in self._pending

	@contextmanager
	def pending(
		self,
		*,
		cancel_key: str | None = None,
		error: type[BaseException] = RuntimeError,
	) -> Iterator[PendingReply]:
		"""Create and park a future until the client reply arrives.

		`cancel_key` groups requests that die together (e.g. all inflight
		requests of one channel), failed via `reject_where`.
		"""
		reply_id = uuid.uuid4().hex
		future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
		self._pending[reply_id] = _Pending(future, cancel_key, error)
		try:
			yield PendingReply(reply_id, future)
		finally:
			self._pending.pop(reply_id, None)

	def apply(self, message: ReplyMessage) -> None:
		"""Resolve or reject from a `reply` packet. Missing ids are no-ops."""
		reply_id = message["id"]
		entry = self._pending.get(reply_id)
		if entry is None:
			return
		error = message.get("error")
		if error is not None:
			self.reject(
				reply_id,
				error if isinstance(error, BaseException) else entry.error(str(error)),
			)
		else:
			self.resolve(reply_id, message.get("payload"))

	def resolve(self, reply_id: str, value: Any) -> None:
		entry = self._pop(reply_id)
		if entry is not None and not entry.future.done():
			entry.future.set_result(value)

	def reject(self, reply_id: str, error: BaseException) -> None:
		entry = self._pop(reply_id)
		if entry is not None and not entry.future.done():
			entry.future.set_exception(error)

	def discard(self, reply_id: str) -> None:
		"""Forget a pending reply without touching its future (timeouts)."""
		self._pop(reply_id)

	def reject_where(self, cancel_key: str, error: BaseException) -> None:
		reply_ids = [
			reply_id
			for reply_id, entry in self._pending.items()
			if entry.cancel_key == cancel_key
		]
		for reply_id in reply_ids:
			self.reject(reply_id, error)

	def cancel_all(self) -> None:
		for entry in self._pending.values():
			if not entry.future.done():
				entry.future.cancel()
		self._pending.clear()

	def _pop(self, reply_id: str) -> _Pending | None:
		return self._pending.pop(reply_id, None)
