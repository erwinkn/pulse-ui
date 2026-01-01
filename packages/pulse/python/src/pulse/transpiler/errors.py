"""Transpiler-specific error classes."""

from __future__ import annotations

import ast


class TranspileError(Exception):
	"""Error during transpilation with optional source location."""

	message: str
	node: ast.expr | ast.stmt | ast.excepthandler | None
	source: str | None
	filename: str | None
	func_name: str | None

	def __init__(
		self,
		message: str,
		*,
		node: ast.expr | ast.stmt | ast.excepthandler | None = None,
		source: str | None = None,
		filename: str | None = None,
		func_name: str | None = None,
	) -> None:
		self.message = message
		self.node = node
		self.source = source
		self.filename = filename
		self.func_name = func_name
		super().__init__(self._format_message())

	def _format_message(self) -> str:
		"""Format the error message with source location if available."""
		parts = [self.message]

		if self.node is not None and hasattr(self.node, "lineno"):
			loc_parts: list[str] = []
			if self.func_name:
				loc_parts.append(f"in {self.func_name}")
			if self.filename:
				loc_parts.append(f"at {self.filename}:{self.node.lineno}")
			else:
				loc_parts.append(f"at line {self.node.lineno}")
			if hasattr(self.node, "col_offset"):
				loc_parts[-1] += f":{self.node.col_offset}"

			if loc_parts:
				parts.append(" ".join(loc_parts))

			# Show the source line if available
			if self.source:
				lines = self.source.splitlines()
				if 0 < self.node.lineno <= len(lines):
					source_line = lines[self.node.lineno - 1]
					parts.append(f"\n  {source_line}")
					# Add caret pointing to column
					if hasattr(self.node, "col_offset"):
						parts.append("  " + " " * self.node.col_offset + "^")

		return "\n".join(parts) if len(parts) > 1 else parts[0]

	def with_context(
		self,
		*,
		node: ast.expr | ast.stmt | ast.excepthandler | None = None,
		source: str | None = None,
		filename: str | None = None,
		func_name: str | None = None,
	) -> TranspileError:
		"""Return a new TranspileError with additional context."""
		return TranspileError(
			self.message,
			node=node or self.node,
			source=source or self.source,
			filename=filename or self.filename,
			func_name=func_name or self.func_name,
		)
