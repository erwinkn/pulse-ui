"""Emit context for code generation."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import Literal


@dataclass
class EmitContext:
	"""Context for emit operations during route code generation.

	Stores information about the current route file being generated,
	allowing emit methods to compute correct relative paths.

	Usage:
		with EmitContext(route_file_path="routes/users/index.tsx"):
			js_code = emit(fn.transpile())
	"""

	route_file_path: str
	"""Path to route file from pulse folder root, e.g. 'routes/users/index.tsx'"""

	_token: Token[EmitContext | None] | None = field(default=None, repr=False)

	@classmethod
	def get(cls) -> EmitContext | None:
		"""Get current emit context, or None if not set."""
		return _EMIT_CONTEXT.get()

	def __enter__(self) -> EmitContext:
		self._token = _EMIT_CONTEXT.set(self)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None = None,
		exc_val: BaseException | None = None,
		exc_tb: TracebackType | None = None,
	) -> Literal[False]:
		if self._token is not None:
			_EMIT_CONTEXT.reset(self._token)
			self._token = None
		return False


_EMIT_CONTEXT: ContextVar[EmitContext | None] = ContextVar("emit_context", default=None)
