"""
Tests for Python module transpilation in v2 transpiler.

Tests module registration, PyModule, Transformer, and built-in module transpilation.
"""

import importlib

import pytest
from pulse.transpiler_v2.nodes import (
	EXPR_REGISTRY,
	Call,
	ExprNode,
	Identifier,
	Literal,
	Member,
	Transformer,
	emit,
	transformer,
)
from pulse.transpiler_v2.py_module import PyModule

# =============================================================================
# Transformer Tests
# =============================================================================


class TestTransformer:
	"""Test Transformer node behavior."""

	def test_transformer_emit_raises(self):
		"""Transformer cannot be emitted directly."""
		t = Transformer(lambda ctx: Literal(1))
		with pytest.raises(TypeError, match="cannot be emitted directly"):
			t.emit([])

	def test_transformer_with_name_in_error(self):
		"""Transformer error includes name if provided."""
		t = Transformer(lambda ctx: Literal(1), name="my_func")
		with pytest.raises(TypeError, match="my_func"):
			out: list[str] = []
			t.emit(out)

	def test_transformer_emit_getattr_raises(self):
		"""Transformer emit_getattr raises TypeError."""
		t = Transformer(lambda ctx: Literal(1), name="my_func")
		# Need a mock ctx
		with pytest.raises(TypeError, match="cannot have attributes"):
			t.emit_getattr("foo", None)  # pyright: ignore[reportArgumentType]

	def test_transformer_emit_subscript_raises(self):
		"""Transformer emit_subscript raises TypeError."""
		t = Transformer(lambda ctx: Literal(1), name="my_func")
		with pytest.raises(TypeError, match="cannot be subscripted"):
			t.emit_subscript("key", None)  # pyright: ignore[reportArgumentType]


class TestTransformerDecorator:
	"""Test the @transformer decorator."""

	def test_decorator_with_name(self):
		"""@transformer("name") creates named Transformer."""

		@transformer("my_len")  # pyright: ignore[reportArgumentType]
		def emit_len(x, *, ctx):
			return Member(ctx.emit_expr(x), "length")

		assert isinstance(emit_len, Transformer)
		assert emit_len.name == "my_len"

	def test_decorator_without_name(self):
		"""@transformer creates Transformer without explicit name."""
		t = transformer(  # pyright: ignore[reportCallIssue]
			lambda x, ctx: Literal(1)  # pyright: ignore[reportArgumentType]
		)
		assert isinstance(t, Transformer)
		assert t.name == ""


# =============================================================================
# PyModule Tests
# =============================================================================


class TestPyModule:
	"""Test PyModule ExprNode behavior."""

	def test_module_expr_emit_raises(self):
		"""PyModule cannot be emitted directly."""
		me = PyModule({"foo": Literal(1)}, name="mymodule")
		with pytest.raises(TypeError, match="cannot be emitted directly"):
			out: list[str] = []
			me.emit(out)

	def test_module_expr_emit_call_raises(self):
		"""PyModule cannot be called."""
		me = PyModule({"foo": Literal(1)}, name="mymodule")
		with pytest.raises(TypeError, match="cannot be called directly"):
			me.emit_call([], {}, None)  # pyright: ignore[reportArgumentType]

	def test_module_expr_emit_subscript_raises(self):
		"""PyModule cannot be subscripted."""
		me = PyModule({"foo": Literal(1)}, name="mymodule")
		with pytest.raises(TypeError, match="cannot be subscripted"):
			me.emit_subscript("key", None)  # pyright: ignore[reportArgumentType]

	def test_module_expr_emit_getattr_returns_expr(self):
		"""PyModule.emit_getattr looks up attribute in transpiler dict."""
		foo_expr = Literal(42)
		me = PyModule({"foo": foo_expr}, name="mymodule")
		result = me.emit_getattr("foo", None)  # pyright: ignore[reportArgumentType]
		assert result is foo_expr

	def test_module_expr_emit_getattr_missing_raises(self):
		"""PyModule.emit_getattr raises for unknown attribute."""
		me = PyModule({"foo": Literal(1)}, name="mymodule")
		with pytest.raises(TypeError, match="has no attribute 'bar'"):
			me.emit_getattr("bar", None)  # pyright: ignore[reportArgumentType]


# =============================================================================
# Module Registration Tests
# =============================================================================


class TestModuleRegistration:
	"""Test module registration system."""

	def test_register_module_with_class(self):
		"""register_module works with a class namespace."""
		import types

		# Create a fake module
		fake_module = types.ModuleType("fake_math")
		fake_module.pi = 3.14159  # pyright: ignore[reportAttributeAccessIssue]
		fake_module.sqrt = lambda x: x**0.5  # pyright: ignore[reportAttributeAccessIssue]

		class FakeMath:
			pi = Member(Identifier("Math"), "PI")

			@staticmethod
			def sqrt(x, *, ctx):
				return Call(Member(Identifier("Math"), "sqrt"), [ctx.emit_expr(x)])

		prev_registry = dict(EXPR_REGISTRY)
		try:
			PyModule.register(fake_module, FakeMath)

			module_expr = EXPR_REGISTRY.get(id(fake_module))
			assert module_expr is not None
			assert isinstance(module_expr, PyModule)
			assert module_expr.name == "fake_math"
			assert "pi" in module_expr.transpiler
			assert "sqrt" in module_expr.transpiler

			# pi should be ExprNode
			assert isinstance(module_expr.transpiler["pi"], ExprNode)

			# sqrt should be Transformer
			assert isinstance(module_expr.transpiler["sqrt"], Transformer)
		finally:
			EXPR_REGISTRY.clear()
			EXPR_REGISTRY.update(prev_registry)

	def test_register_module_with_dict(self):
		"""register_module works with dict."""
		import types

		fake_module = types.ModuleType("fake_json")
		fake_module.dumps = lambda x: str(x)  # pyright: ignore[reportAttributeAccessIssue]

		transpilation = {
			"dumps": lambda obj, *, ctx: Call(
				Member(Identifier("JSON"), "stringify"), [ctx.emit_expr(obj)]
			)
		}

		prev_registry = dict(EXPR_REGISTRY)
		try:
			PyModule.register(fake_module, transpilation)  # pyright: ignore[reportArgumentType]

			module_expr = EXPR_REGISTRY.get(id(fake_module))
			assert module_expr is not None
			assert isinstance(module_expr, PyModule)
			assert "dumps" in module_expr.transpiler
			assert isinstance(module_expr.transpiler["dumps"], Transformer)
		finally:
			EXPR_REGISTRY.clear()
			EXPR_REGISTRY.update(prev_registry)


# =============================================================================
# Math Module Tests
# =============================================================================


class TestMathModule:
	"""Test math module transpilation."""

	def test_math_sqrt(self):
		"""math.sqrt transpiles to Math.sqrt."""
		from pulse.transpiler_v2.modules.math import PyMath

		# Mock context that just returns the identifier
		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.sqrt("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.sqrt(x)"

	def test_math_sin(self):
		"""math.sin transpiles to Math.sin."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.sin("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.sin(x)"

	def test_math_cos(self):
		"""math.cos transpiles to Math.cos."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.cos("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.cos(x)"

	def test_math_log(self):
		"""math.log transpiles to Math.log."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.log("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.log(x)"

	def test_math_log_with_base(self):
		"""math.log(x, base) transpiles to Math.log(x) / Math.log(base)."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				if x == "x":
					return Identifier("x")
				return Literal(10)

		result = PyMath.log("x", 10, ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.log(x) / Math.log(10)"

	def test_math_floor(self):
		"""math.floor transpiles to Math.floor."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.floor("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.floor(x)"

	def test_math_ceil(self):
		"""math.ceil transpiles to Math.ceil."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, x):
				return Identifier("x")

		result = PyMath.ceil("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.ceil(x)"

	def test_math_pi_constant(self):
		"""math.pi transpiles to Math.PI."""
		from pulse.transpiler_v2.modules.math import PyMath

		assert emit(PyMath.pi) == "Math.PI"

	def test_math_e_constant(self):
		"""math.e transpiles to Math.E."""
		from pulse.transpiler_v2.modules.math import PyMath

		assert emit(PyMath.e) == "Math.E"

	def test_math_tau_constant(self):
		"""math.tau transpiles to 2 * Math.PI."""
		from pulse.transpiler_v2.modules.math import PyMath

		assert emit(PyMath.tau) == "2 * Math.PI"

	def test_math_inf_constant(self):
		"""math.inf transpiles to Infinity."""
		from pulse.transpiler_v2.modules.math import PyMath

		assert emit(PyMath.inf) == "Infinity"

	def test_math_nan_constant(self):
		"""math.nan transpiles to NaN."""
		from pulse.transpiler_v2.modules.math import PyMath

		assert emit(PyMath.nan) == "NaN"

	def test_math_pow(self):
		"""math.pow transpiles to Math.pow."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				if val == "x":
					return Identifier("x")
				return Identifier("y")

		result = PyMath.pow("x", "y", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.pow(x, y)"

	def test_math_hypot(self):
		"""math.hypot transpiles to Math.hypot."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				if val == "x":
					return Identifier("x")
				return Identifier("y")

		result = PyMath.hypot("x", "y", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.hypot(x, y)"

	def test_math_radians(self):
		"""math.radians transpiles to x * (Math.PI / 180)."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("degrees")

		result = PyMath.radians("degrees", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert "Math.PI" in emit(result)
		assert "180" in emit(result)

	def test_math_degrees(self):
		"""math.degrees transpiles to x * (180 / Math.PI)."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("radians")

		result = PyMath.degrees("radians", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert "Math.PI" in emit(result)
		assert "180" in emit(result)

	def test_math_isnan(self):
		"""math.isnan transpiles to Number.isNaN."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("x")

		result = PyMath.isnan("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Number.isNaN(x)"

	def test_math_isfinite(self):
		"""math.isfinite transpiles to Number.isFinite."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("x")

		result = PyMath.isfinite("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Number.isFinite(x)"

	def test_math_trunc(self):
		"""math.trunc transpiles to Math.trunc."""
		from pulse.transpiler_v2.modules.math import PyMath

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("x")

		result = PyMath.trunc("x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Math.trunc(x)"


# =============================================================================
# JSON Module Tests
# =============================================================================


class TestJsonModule:
	"""Test json module transpilation."""

	def test_json_dumps(self):
		"""json.dumps transpiles to JSON.stringify."""
		from pulse.transpiler_v2.modules.json import PyJson

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("obj")

		result = PyJson.dumps("obj", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "JSON.stringify(obj)"

	def test_json_loads(self):
		"""json.loads transpiles to JSON.parse."""
		from pulse.transpiler_v2.modules.json import PyJson

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("s")

		result = PyJson.loads("s", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "JSON.parse(s)"


# =============================================================================
# Asyncio Module Tests
# =============================================================================


class TestAsyncioModule:
	"""Test asyncio module transpilation."""

	def test_asyncio_gather_default(self):
		"""asyncio.gather transpiles to Promise.all by default."""
		from pulse.transpiler_v2.modules.asyncio import PyAsyncio

		class MockCtx:
			def emit_expr(self, val):
				if val == "a":
					return Identifier("a")
				return Identifier("b")

		result = PyAsyncio.gather("a", "b", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Promise.all([a, b])"

	def test_asyncio_gather_return_exceptions_true(self):
		"""asyncio.gather(return_exceptions=True) transpiles to Promise.allSettled."""
		from pulse.transpiler_v2.modules.asyncio import PyAsyncio

		class MockCtx:
			def emit_expr(self, val):
				if val == "a":
					return Identifier("a")
				return Identifier("b")

		result = PyAsyncio.gather("a", "b", return_exceptions=True, ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "Promise.allSettled([a, b])"


# =============================================================================
# Typing Module Tests
# =============================================================================


class TestTypingModule:
	"""Test typing module transpilation."""

	def test_typing_cast_returns_value(self):
		"""typing.cast is a no-op and returns the value."""
		from pulse.transpiler_v2.modules.typing import PyTyping

		class MockCtx:
			def emit_expr(self, val):
				return Identifier("x")

		result = PyTyping.cast(int, "x", ctx=MockCtx())  # pyright: ignore[reportArgumentType]
		assert emit(result) == "x"

	def test_typing_any_emit_raises(self):
		"""typing.Any cannot be emitted directly."""
		from pulse.transpiler_v2.modules.typing import PyTyping

		with pytest.raises(TypeError, match="cannot be emitted"):
			out: list[str] = []
			PyTyping.Any.emit(out)

	def test_typing_any_subscript_returns_type_hint(self):
		"""Subscripting a type hint returns another type hint."""
		from pulse.transpiler_v2.modules.typing import PyTyping, TypeHint

		result = PyTyping.List.emit_subscript(int, None)  # pyright: ignore[reportArgumentType]
		assert isinstance(result, TypeHint)
		assert "List" in result.name

	def test_typing_optional_emit_raises(self):
		"""typing.Optional cannot be emitted directly."""
		from pulse.transpiler_v2.modules.typing import PyTyping

		with pytest.raises(TypeError, match="cannot be emitted"):
			out: list[str] = []
			PyTyping.Optional.emit(out)


# =============================================================================
# Module Registration Integration
# =============================================================================


class TestModuleRegistrationIntegration:
	"""Test that built-in modules are properly registered."""

	def test_math_module_registered(self):
		"""math module is registered after importing modules."""
		import math

		# Import to trigger registration
		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		assert EXPR_REGISTRY.get(id(math)) is not None

	def test_json_module_registered(self):
		"""json module is registered after importing modules."""
		import json

		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		assert EXPR_REGISTRY.get(id(json)) is not None

	def test_asyncio_module_registered(self):
		"""asyncio module is registered after importing modules."""
		import asyncio

		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		assert EXPR_REGISTRY.get(id(asyncio)) is not None

	def test_typing_module_registered(self):
		"""typing module is registered after importing modules."""
		import typing

		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		assert EXPR_REGISTRY.get(id(typing)) is not None

	def test_math_sqrt_in_registry(self):
		"""math.sqrt is registered in EXPR_REGISTRY."""
		import math

		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		result = EXPR_REGISTRY.get(id(math.sqrt))
		assert result is not None
		assert isinstance(result, Transformer)

	def test_math_pi_in_registry(self):
		"""math.pi is registered in EXPR_REGISTRY."""
		import math

		import pulse.transpiler_v2.modules as modules

		importlib.reload(modules)

		result = EXPR_REGISTRY.get(id(math.pi))
		assert result is not None
		assert emit(result) == "Math.PI"
