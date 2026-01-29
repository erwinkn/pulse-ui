"""Cached parsing helpers for transpiler source inspection."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pulse.helpers import getsourcecode
from pulse.transpiler.errors import TranspileError


@dataclass(slots=True)
class ParsedSource:
	source: str
	filename: str | None
	source_start_line: int | None


_SOURCE_CACHE: dict[Callable[..., Any], ParsedSource] = {}
_AST_CACHE: dict[Callable[..., Any], ast.FunctionDef | ast.AsyncFunctionDef] = {}


def clear_parse_cache() -> None:
	_SOURCE_CACHE.clear()
	_AST_CACHE.clear()


def get_source(fn: Callable[..., Any]) -> ParsedSource:
	cached = _SOURCE_CACHE.get(fn)
	if cached is not None:
		return cached

	src = getsourcecode(fn)
	src = textwrap.dedent(src)
	try:
		source_start_line = inspect.getsourcelines(fn)[1]
	except (OSError, TypeError):
		source_start_line = None
	try:
		filename = inspect.getfile(fn)
	except (TypeError, OSError):
		filename = None

	parsed = ParsedSource(
		source=src,
		filename=filename,
		source_start_line=source_start_line,
	)
	_SOURCE_CACHE[fn] = parsed
	return parsed


def get_ast(fn: Callable[..., Any]) -> ast.FunctionDef | ast.AsyncFunctionDef:
	cached = _AST_CACHE.get(fn)
	if cached is not None:
		return cached

	module = ast.parse(get_source(fn).source)
	fndefs = [
		n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
	]
	if not fndefs:
		raise TranspileError("No function definition found in source")
	fndef = fndefs[-1]
	_AST_CACHE[fn] = fndef
	return fndef
