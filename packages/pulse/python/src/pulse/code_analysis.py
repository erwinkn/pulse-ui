"""Code analysis utilities for inspecting Python source."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any


def is_stub_function(fn: Callable[..., Any]) -> bool:
	"""Check if function body is just ... or pass (no real implementation)."""
	try:
		source = inspect.getsource(fn)
		tree = ast.parse(textwrap.dedent(source))
		func_def = tree.body[0]
		if not isinstance(func_def, ast.FunctionDef):
			return False
		body = func_def.body
		# Skip docstring
		if body and isinstance(body[0], ast.Expr):
			if isinstance(body[0].value, ast.Constant) and isinstance(
				body[0].value.value, str
			):
				body = body[1:]
		if not body:
			return True
		if len(body) == 1:
			stmt = body[0]
			if isinstance(stmt, ast.Pass):
				return True
			if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
				if stmt.value.value is ...:
					return True
		return False
	except (OSError, TypeError):
		return False
