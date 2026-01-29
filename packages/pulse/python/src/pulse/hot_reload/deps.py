from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

from pulse.transpiler.function import analyze_code_object, analyze_deps

_active_module_index: Any | None = None
_UNKNOWN_DEPS: dict[int, bool] = {}


def set_active_module_index(index: Any | None) -> None:
	global _active_module_index
	_active_module_index = index


def compute_component_deps(fn: Any) -> set[str]:
	deps, unknown = _compute_component_deps(fn)
	_UNKNOWN_DEPS[id(fn)] = unknown
	return deps


def get_unknown_deps(fn: Any) -> bool:
	return _UNKNOWN_DEPS.get(id(fn), False)


def _is_reloadable_module(module_name: str) -> bool:
	index = _active_module_index
	if index is None:
		return False
	info = index.by_name.get(module_name)
	return info is not None and info.reloadable


def _collect_local_imports(fn: Any) -> tuple[set[str], bool]:
	try:
		source = inspect.getsource(fn)
	except (OSError, TypeError):
		return set(), True

	source = textwrap.dedent(source)
	try:
		tree = ast.parse(source)
	except SyntaxError:
		return set(), True

	target = None
	name = getattr(fn, "__name__", "")
	for node in ast.walk(tree):
		if (
			isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
			and node.name == name
		):
			target = node
			break
	if target is None:
		return set(), True

	imports: set[str] = set()
	unknown = False
	for node in target.body:
		if isinstance(node, ast.Import):
			for alias in node.names:
				imports.add(alias.name)
		if isinstance(node, ast.ImportFrom):
			resolved = _resolve_from_import(fn, node)
			if not resolved:
				unknown = True
			else:
				imports.update(resolved)
	return imports, unknown


def _resolve_from_import(fn: Any, node: ast.ImportFrom) -> set[str]:
	module_name = getattr(fn, "__module__", "")
	level = node.level or 0
	base_parts = module_name.split(".")
	if level:
		if len(base_parts) < level:
			return set()
		base_parts = base_parts[:-level]
	module = node.module
	if module:
		base_parts += module.split(".")
	base = ".".join([p for p in base_parts if p])
	resolved: set[str] = set()
	if base:
		resolved.add(base)
	for alias in node.names:
		if alias.name == "*":
			continue
		if base:
			resolved.add(f"{base}.{alias.name}")
	return resolved


def _resolve_module_for_value(value: Any) -> str | None:
	if inspect.ismodule(value):
		return getattr(value, "__name__", None)
	if inspect.isfunction(value) or inspect.isclass(value):
		mod = inspect.getmodule(value)
		return getattr(mod, "__name__", None) if mod else None
	mod = inspect.getmodule(value)
	if mod is not None:
		return getattr(mod, "__name__", None)
	return None


def _compute_component_deps(fn: Any) -> tuple[set[str], bool]:
	unknown = False
	try:
		analyze_deps(fn)
	except Exception:
		unknown = True

	try:
		effective_globals, all_names = analyze_code_object(fn)
	except Exception:
		return set(), True

	deps: set[str] = set()
	local_imports, import_unknown = _collect_local_imports(fn)
	unknown = unknown or import_unknown

	for name in local_imports:
		if _is_reloadable_module(name):
			deps.add(name)

	for name in all_names:
		value = effective_globals.get(name)
		if value is None:
			continue
		module_name = _resolve_module_for_value(value)
		if module_name is None:
			unknown = True
			continue
		if _is_reloadable_module(module_name):
			deps.add(module_name)

	return deps, unknown


__all__ = [
	"compute_component_deps",
	"get_unknown_deps",
	"set_active_module_index",
]
