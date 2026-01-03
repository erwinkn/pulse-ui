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
	source_start_line: int | None

	def __init__(
		self,
		message: str,
		*,
		node: ast.expr | ast.stmt | ast.excepthandler | None = None,
		source: str | None = None,
		filename: str | None = None,
		func_name: str | None = None,
		source_start_line: int | None = None,
	) -> None:
		self.message = message
		self.node = node
		self.source = source
		self.filename = filename
		self.func_name = func_name
		self.source_start_line = source_start_line
		super().__init__(self._format_message())

	def _format_message(self) -> str:
		"""Format the error message with source location if available."""
		parts = [self.message]

		if self.node is not None and hasattr(self.node, "lineno"):
			loc_parts: list[str] = []
			if self.func_name:
				loc_parts.append(f"in {self.func_name}")
			display_lineno = self.node.lineno
			if self.source_start_line is not None:
				display_lineno = self.source_start_line + self.node.lineno - 1
			if self.filename:
				loc_parts.append(f"at {self.filename}:{display_lineno}")
			else:
				loc_parts.append(f"at line {display_lineno}")

			display_line = None
			display_col = None
			if self.source:
				lines = self.source.splitlines()
				if 0 < self.node.lineno <= len(lines):
					source_line = lines[self.node.lineno - 1]
					display_line = source_line.expandtabs(4)
					if hasattr(self.node, "col_offset"):
						prefix = source_line[: self.node.col_offset]
						display_col = len(prefix.expandtabs(4))

			if hasattr(self.node, "col_offset"):
				col = display_col if display_col is not None else self.node.col_offset
				loc_parts[-1] += f":{col}"

			if loc_parts:
				parts.append(" ".join(loc_parts))

			# Show the source line if available
			if display_line is not None:
				parts.append(f"\n  {display_line}")
				# Add caret pointing to column
				if display_col is not None:
					parts.append("  " + " " * display_col + "^")

		return "\n".join(parts) if len(parts) > 1 else parts[0]

	def with_context(
		self,
		*,
		node: ast.expr | ast.stmt | ast.excepthandler | None = None,
		source: str | None = None,
		filename: str | None = None,
		func_name: str | None = None,
		source_start_line: int | None = None,
	) -> TranspileError:
		"""Return a new TranspileError with additional context."""
		return TranspileError(
			self.message,
			node=node or self.node,
			source=source or self.source,
			filename=filename or self.filename,
			func_name=func_name or self.func_name,
			source_start_line=source_start_line or self.source_start_line,
		)
