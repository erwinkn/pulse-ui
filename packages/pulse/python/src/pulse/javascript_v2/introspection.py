"""Introspection utilities for analyzing function dependencies via code objects.

This module provides helpers to recursively extract all names referenced by a function,
including names used in nested function definitions. This is necessary because
`inspect.getclosurevars()` only captures names in the immediate function body.
"""

from __future__ import annotations

import builtins
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pulse.javascript_v2.utils import AnyCallable


@dataclass
class FunctionRefs:
	"""All name references found in a function and its nested functions."""

	globals: dict[str, Any]
	"""Names that resolve to entries in the function's __globals__."""

	builtins: dict[str, Any]
	"""Names that resolve to Python builtins (map, len, etc.)."""

	unresolved: set[str]
	"""Names found in co_names that don't resolve to globals or builtins.
	These are typically attribute names (e.g., 'pi' from 'math.pi')."""


def get_code_names(fn: AnyCallable) -> set[str]:
	"""Recursively collect all names from a function's code object and nested functions.

	This walks the code object tree via co_consts to find nested function definitions
	and collects co_names from each.

	Args:
	    fn: The function to analyze.

	Returns:
	    Set of all names referenced (globals, attributes, etc.)
	"""
	seen: set[int] = set()
	names: set[str] = set()

	def walk(code: types.CodeType) -> None:
		if id(code) in seen:
			return
		seen.add(id(code))
		names.update(code.co_names)
		for const in code.co_consts:
			if isinstance(const, types.CodeType):
				walk(const)

	walk(fn.__code__)
	return names


def get_function_refs(fn: AnyCallable) -> FunctionRefs:
	"""Analyze a function and categorize all its name references.

	Args:
	    fn: The function to analyze.

	Returns:
	    FunctionRefs with globals, builtins, and unresolved names.
	"""
	all_names = get_code_names(fn)

	fn_globals = fn.__globals__
	builtin_dict = vars(builtins)

	globals_found: dict[str, Any] = {}
	builtins_found: dict[str, Any] = {}
	unresolved: set[str] = set()

	for name in all_names:
		if name in fn_globals:
			globals_found[name] = fn_globals[name]
		elif name in builtin_dict:
			builtins_found[name] = builtin_dict[name]
		else:
			unresolved.add(name)

	return FunctionRefs(
		globals=globals_found,
		builtins=builtins_found,
		unresolved=unresolved,
	)


def validate_no_nonlocals(fn: Callable[..., Any]) -> None:
	"""Raise if the function has nonlocal references (is a closure).

	Args:
	    fn: The function to check.

	Raises:
	    ValueError: If the function captures nonlocal variables.
	"""
	code = fn.__code__
	if code.co_freevars:
		raise ValueError(
			f"Function {fn.__name__} captures nonlocal variables: {code.co_freevars}. "
			+ "Functions defined inside other functions are not supported for transpilation."
		)
