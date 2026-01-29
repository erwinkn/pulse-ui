from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from dataclasses import dataclass
from typing import Any, override


@dataclass(frozen=True, slots=True)
class HookSignatureEntry:
	kind: str
	key_literal: str | None
	lineno: int
	col: int


_HOOK_KINDS = {"state", "effect", "init", "setup"}


def compute_component_signature(fn: Any) -> str | None:
	_, digest = compute_component_signature_data(fn)
	return digest


def compute_component_signature_data(
	fn: Any,
) -> tuple[list[HookSignatureEntry] | None, str | None]:
	try:
		source = inspect.getsource(fn)
	except (OSError, TypeError):
		return None, None

	source = textwrap.dedent(source)
	try:
		tree = ast.parse(source)
	except SyntaxError:
		return None, None

	target = _find_target_def(tree, getattr(fn, "__name__", ""))
	if target is None:
		return None, None

	collector = _HookSignatureCollector(fn, target)
	collector.visit(target)
	entries = collector.entries

	payload = [
		{
			"kind": entry.kind,
			"key": entry.key_literal,
			"line": entry.lineno,
			"col": entry.col,
		}
		for entry in entries
	]
	encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
	digest = hashlib.sha1(encoded).hexdigest()
	return entries, digest


def _find_target_def(
	tree: ast.AST, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
	for node in ast.walk(tree):
		if (
			isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
			and node.name == name
		):
			return node
	return None


def _extract_key_literal(node: ast.AST) -> str | None:
	if isinstance(node, ast.Constant) and isinstance(node.value, str):
		return node.value
	return None


def _is_pulse_module(obj: Any) -> bool:
	return inspect.ismodule(obj) and getattr(obj, "__name__", None) == "pulse"


def _is_pulse_hook(obj: Any, kind: str) -> bool:
	name = getattr(obj, "__name__", None)
	module = getattr(obj, "__module__", "")
	if name != kind:
		return False
	return module.startswith("pulse")


class _HookSignatureCollector(ast.NodeVisitor):
	def __init__(
		self,
		fn: Any,
		root: ast.FunctionDef | ast.AsyncFunctionDef,
	) -> None:
		self.entries: list[HookSignatureEntry] = []
		self._root: ast.FunctionDef | ast.AsyncFunctionDef = root
		self._module_aliases: set[str] = set()
		self._direct_hooks: dict[str, str] = {}
		self._init_from_globals(fn)
		self._init_from_local_imports(root)

	def _init_from_globals(self, fn: Any) -> None:
		globals_map = getattr(fn, "__globals__", {}) or {}
		for name, value in globals_map.items():
			if _is_pulse_module(value):
				self._module_aliases.add(name)
				continue
			for kind in _HOOK_KINDS:
				if _is_pulse_hook(value, kind):
					self._direct_hooks[name] = kind

	def _init_from_local_imports(
		self,
		root: ast.FunctionDef | ast.AsyncFunctionDef,
	) -> None:
		for node in root.body:
			if isinstance(node, ast.Import):
				for alias in node.names:
					if alias.name == "pulse":
						self._module_aliases.add(alias.asname or alias.name)
			if isinstance(node, ast.ImportFrom):
				if node.module != "pulse":
					continue
				for alias in node.names:
					kind = alias.name
					if kind in _HOOK_KINDS:
						self._direct_hooks[alias.asname or alias.name] = kind

	def _record(self, kind: str, node: ast.AST, key_literal: str | None) -> None:
		lineno = getattr(node, "lineno", 0)
		col = getattr(node, "col_offset", 0)
		self.entries.append(
			HookSignatureEntry(
				kind=kind,
				key_literal=key_literal,
				lineno=lineno,
				col=col,
			)
		)

	def _match_call(self, node: ast.AST) -> tuple[str | None, str | None]:
		if isinstance(node, ast.Name):
			kind = self._direct_hooks.get(node.id)
			return kind, None
		if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
			if node.value.id in self._module_aliases and node.attr in _HOOK_KINDS:
				return node.attr, None
		return None, None

	def _match_call_with_key(self, call: ast.Call) -> tuple[str | None, str | None]:
		kind, _ = self._match_call(call.func)
		if kind is None:
			return None, None
		key_literal: str | None = None
		for kw in call.keywords:
			if kw.arg == "key":
				key_literal = _extract_key_literal(kw.value)
				break
		return kind, key_literal

	def _handle_decorator(self, dec: ast.AST) -> None:
		if isinstance(dec, ast.Call):
			kind, key_literal = self._match_call_with_key(dec)
			if kind == "effect":
				self._record("effect", dec, key_literal)
			return
		kind, _ = self._match_call(dec)
		if kind == "effect":
			self._record("effect", dec, None)

	@override
	def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
		if node is self._root:
			for stmt in node.body:
				self.visit(stmt)
			return
		for dec in node.decorator_list:
			self._handle_decorator(dec)

	@override
	def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
		if node is self._root:
			for stmt in node.body:
				self.visit(stmt)
			return
		for dec in node.decorator_list:
			self._handle_decorator(dec)

	@override
	def visit_Lambda(self, node: ast.Lambda) -> None:
		return

	@override
	def visit_ClassDef(self, node: ast.ClassDef) -> None:
		return

	@override
	def visit_With(self, node: ast.With) -> None:
		for item in node.items:
			ctx = item.context_expr
			if isinstance(ctx, ast.Call):
				kind, key_literal = self._match_call_with_key(ctx)
				if kind == "init":
					self._record("init", ctx, key_literal)
					continue
				self.visit(ctx)
			else:
				self.visit(ctx)
		for stmt in node.body:
			self.visit(stmt)

	@override
	def visit_Call(self, node: ast.Call) -> None:
		kind, key_literal = self._match_call_with_key(node)
		if kind in {"state", "effect", "setup"}:
			self._record(kind, node, key_literal)
		self.generic_visit(node)

	@override
	def generic_visit(self, node: ast.AST) -> None:
		for child in ast.iter_child_nodes(node):
			self.visit(child)


__all__ = [
	"HookSignatureEntry",
	"compute_component_signature",
	"compute_component_signature_data",
]
