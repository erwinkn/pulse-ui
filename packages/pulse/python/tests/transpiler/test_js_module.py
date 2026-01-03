"""Tests for pulse.js.* module integration in transpiler."""

from __future__ import annotations

import ast
from collections.abc import Iterator

import pytest
from pulse.transpiler import (
	EXPR_REGISTRY,
	Identifier,
	Import,
	JsModule,
	Member,
	New,
	emit,
)
from pulse.transpiler.imports import clear_import_registry
from pulse.transpiler.js_module import Class


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> Iterator[None]:
	# Keep EXPR_REGISTRY stable across the suite: other tests rely on global module
	# registrations (e.g. pulse.js.* modules registering ModuleRef).
	prev_registry = dict(EXPR_REGISTRY)
	clear_import_registry()
	yield
	EXPR_REGISTRY.clear()
	EXPR_REGISTRY.update(prev_registry)


class TestJsModule:
	"""Test JsModule configuration."""

	def test_builtin_module_to_expr(self) -> None:
		"""Builtin modules return Identifier from to_expr."""
		module = JsModule(name="Math")
		expr = module.to_expr()
		assert isinstance(expr, Identifier)
		assert expr.name == "Math"

	def test_builtin_is_builtin(self) -> None:
		"""Builtins report is_builtin=True."""
		module = JsModule(name="Math")
		assert module.is_builtin

	def test_external_module_to_expr_namespace(self) -> None:
		"""External namespace modules return Import from to_expr."""
		module = JsModule(name="React", src="react")
		expr = module.to_expr()
		assert isinstance(expr, Import)
		assert expr.name == "React"
		assert expr.src == "react"
		assert not expr.is_default

	def test_external_module_to_expr_default(self) -> None:
		"""External default imports return Import with is_default."""
		module = JsModule(name="lodash", src="lodash", kind="default")
		expr = module.to_expr()
		assert isinstance(expr, Import)
		assert expr.name == "lodash"
		assert expr.is_default

	def test_name_none_to_expr_raises(self) -> None:
		"""Modules with name=None cannot be imported as a whole."""
		from pulse.transpiler.errors import TranspileError

		module = JsModule(name=None, py_name="pulse.js.set")
		with pytest.raises(TranspileError, match="Cannot import module"):
			module.to_expr()

	def test_get_value_builtin(self) -> None:
		"""get_value for builtins returns Member."""
		module = JsModule(name="Math")
		expr = module.get_value("floor")
		assert isinstance(expr, Member)
		assert isinstance(expr.obj, Identifier)
		assert expr.obj.name == "Math"
		assert expr.prop == "floor"

	def test_get_value_builtin_namespace(self) -> None:
		"""Builtin namespaces always return Member (Math.floor, not floor)."""
		module = JsModule(name="Math")
		expr = module.get_value("Math")
		# Even Math.Math returns Member - builtin namespaces are real JS objects
		assert isinstance(expr, Member)
		assert emit(expr) == "Math.Math"

	def test_get_value_name_none(self) -> None:
		"""get_value for name=None returns Identifier."""
		module = JsModule(name=None)
		expr = module.get_value("Set")
		assert isinstance(expr, Identifier)
		assert expr.name == "Set"

	def test_get_value_constructor(self) -> None:
		"""get_value returns a Class when name is in constructors."""
		module = JsModule(name=None, constructors=frozenset({"Set"}))
		expr = module.get_value("Set")
		assert isinstance(expr, Class)

	def test_get_value_named_import(self) -> None:
		"""get_value for external with named_import returns Import."""
		module = JsModule(name="react", src="react", values="named_import")
		expr = module.get_value("useState")
		assert isinstance(expr, Import)
		assert expr.name == "useState"
		assert expr.src == "react"

	def test_get_value_member(self) -> None:
		"""get_value for external with member returns Member."""
		clear_import_registry()
		module = JsModule(name="React", src="react", kind="namespace", values="member")
		expr = module.get_value("useState")
		assert isinstance(expr, Member)
		assert isinstance(expr.obj, Import)
		assert expr.prop == "useState"


class TestClassNode:
	"""Test Class behavior."""

	def test_emit_call_produces_new(self) -> None:
		module = JsModule(name=None, constructors=frozenset({"Set"}))
		ctor = module.get_value("Set")
		assert isinstance(ctor, Class)

		# Minimal mock transpiler
		class MockTranspiler:
			def emit_expr(self, v: object) -> Identifier:
				return Identifier("x")

		ctx = MockTranspiler()
		result = ctor.transpile_call([ast.Constant(value="x")], {}, ctx)  # pyright: ignore[reportArgumentType]
		assert isinstance(result, New)
		assert emit(result) == "new Set(x)"


class TestNew:
	"""Test New node."""

	def test_emit_no_args(self) -> None:
		"""New emits with no args."""
		node = New(Identifier("Set"), [])
		assert emit(node) == "new Set()"

	def test_emit_with_args(self) -> None:
		"""New emits with args."""
		from pulse.transpiler import Array, Literal

		node = New(Identifier("Set"), [Array([Literal(1), Literal(2)])])
		assert emit(node) == "new Set([1, 2])"

	def test_emit_member_constructor(self) -> None:
		"""New works with Member as constructor."""
		node = New(Member(Identifier("window"), "Set"), [])
		assert emit(node) == "new window.Set()"


class TestJsModuleExpr:
	"""Test JsModule Expr behavior when used as a module reference."""

	def test_emit_raises(self) -> None:
		"""JsModule cannot be emitted directly."""
		ref = JsModule(name="Math", py_name="pulse.js.math")
		with pytest.raises(TypeError, match="cannot be emitted"):
			emit(ref)

	def test_emit_call_raises(self) -> None:
		"""JsModule cannot be called directly."""

		class MockCtx:
			pass

		ref = JsModule(name="Math", py_name="pulse.js.math")
		with pytest.raises(TypeError, match="cannot be called"):
			ref.transpile_call([], {}, MockCtx())  # pyright: ignore[reportArgumentType]

	def test_emit_getattr(self) -> None:
		"""JsModule.transpile_getattr returns module value."""

		class MockCtx:
			pass

		ref = JsModule(name="Math", py_name="pulse.js.math")
		expr = ref.transpile_getattr("floor", MockCtx())  # pyright: ignore[reportArgumentType]
		assert isinstance(expr, Member)
		assert emit(expr) == "Math.floor"
