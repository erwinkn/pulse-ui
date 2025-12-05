"""Tests for the JSExpr system and interpreted mode."""

import pytest
from pulse.transpiler.context import interpreted_mode, is_interpreted_mode
from pulse.transpiler.imports import Import, clear_import_registry
from pulse.transpiler.nodes import (
	JSArray,
	JSBoolean,
	JSCall,
	JSMember,
	JSNull,
	JSNumber,
	JSObjectExpr,
	JSString,
	to_js_expr,
)


@pytest.fixture(autouse=True)
def clear_registry() -> None:
	"""Clear import registry between tests."""
	clear_import_registry()


class TestInterpretedModeContext:
	"""Tests for the interpreted_mode context manager."""

	def test_default_is_false(self) -> None:
		"""Default mode is not interpreted."""
		assert not is_interpreted_mode()

	def test_context_manager_enables_mode(self) -> None:
		"""Context manager enables interpreted mode."""
		assert not is_interpreted_mode()
		with interpreted_mode():
			assert is_interpreted_mode()
		assert not is_interpreted_mode()

	def test_nested_context_managers(self) -> None:
		"""Nested context managers work correctly."""
		with interpreted_mode():
			assert is_interpreted_mode()
			with interpreted_mode():
				assert is_interpreted_mode()
			assert is_interpreted_mode()
		assert not is_interpreted_mode()


class TestImportEmit:
	"""Tests for Import.emit() in different modes."""

	def test_emit_normal_mode(self) -> None:
		"""emit() in normal mode returns js_name."""
		imp = Import("Button", "@mantine/core")
		result = imp.emit()
		assert result == f"Button_{imp.id}"

	def test_emit_interpreted_mode(self) -> None:
		"""emit() in interpreted mode returns get_object call."""
		imp = Import("Button", "@mantine/core")
		with interpreted_mode():
			result = imp.emit()
		assert result == f"get_object('Button_{imp.id}')"

	def test_emit_with_member_access_normal_mode(self) -> None:
		"""emit() with member access in normal mode."""
		styles = Import("styles", "./app.module.css")
		member = styles.container
		result = member.emit()
		assert result == f"styles_{styles.id}.container"

	def test_emit_with_member_access_interpreted_mode(self) -> None:
		"""emit() with member access in interpreted mode."""
		styles = Import("styles", "./app.module.css")
		member = styles.container
		with interpreted_mode():
			result = member.emit()
		assert result == f"get_object('styles_{styles.id}').container"

	def test_default_import_emit(self) -> None:
		"""Default import emit works correctly."""
		imp = Import.default("React", "react")
		result = imp.emit()
		assert result == f"React_{imp.id}"

		with interpreted_mode():
			result = imp.emit()
		assert result == f"get_object('React_{imp.id}')"


class TestImportGetattr:
	"""Tests for Import.__getattr__ returning JSMember."""

	def test_getattr_returns_jsmember(self) -> None:
		"""Accessing a property returns JSMember."""
		styles = Import("styles", "./app.module.css")
		result = styles.container
		assert isinstance(result, JSMember)

	def test_jsmember_emit_normal(self) -> None:
		"""JSMember emit in normal mode."""
		styles = Import("styles", "./app.module.css")
		member = styles.container
		result = member.emit()
		assert result == f"styles_{styles.id}.container"

	def test_jsmember_emit_interpreted(self) -> None:
		"""JSMember emit in interpreted mode."""
		styles = Import("styles", "./app.module.css")
		member = styles.container
		with interpreted_mode():
			result = member.emit()
		assert result == f"get_object('styles_{styles.id}').container"

	def test_chained_property_access(self) -> None:
		"""Chained property access is not yet supported on JSMember."""
		# Note: JSMember currently doesn't support __getattr__ for chaining
		# This test documents the current behavior
		obj = Import("myModule", "./my-module")
		member = obj.foo
		result = member.emit()
		assert f"myModule_{obj.id}.foo" == result
		# Chained access would require JSMember to also implement __getattr__
		# For now, users must use Import directly for each property level


class TestImportCall:
	"""Tests for Import.__call__ returning JSCall."""

	def test_call_returns_jscall(self) -> None:
		"""Calling import returns JSCall."""
		cn = Import("cn", "clsx")
		result = cn("a", "b")
		assert isinstance(result, JSCall)

	def test_jscall_emit_no_args(self) -> None:
		"""JSCall emit with no arguments."""
		fn = Import("init", "./utils")
		call = fn()
		result = call.emit()
		assert result == f"init_{fn.id}()"

	def test_jscall_emit_with_string_args(self) -> None:
		"""JSCall emit with string arguments."""
		cn = Import("cn", "clsx")
		call = cn("p-4", "bg-red")
		result = call.emit()
		# JSString uses double quotes
		assert result == f'cn_{cn.id}("p-4", "bg-red")'

	def test_jscall_emit_with_mixed_args(self) -> None:
		"""JSCall emit with mixed argument types."""
		fn = Import("myFunc", "./utils")
		call = fn("hello", 42, True, None)
		result = call.emit()
		# JSString uses double quotes
		assert result == f'myFunc_{fn.id}("hello", 42, true, null)'

	def test_jscall_emit_interpreted(self) -> None:
		"""JSCall emit in interpreted mode."""
		cn = Import("cn", "clsx")
		call = cn("p-4")
		with interpreted_mode():
			result = call.emit()
		# JSString uses double quotes
		assert result == f"get_object('cn_{cn.id}')(\"p-4\")"

	def test_jscall_with_import_arg(self) -> None:
		"""JSCall with Import as argument."""
		fn = Import("process", "./utils")
		data = Import("data", "./data")
		call = fn(data)
		result = call.emit()
		assert result == f"process_{fn.id}(data_{data.id})"

	def test_jscall_with_jsmember_arg(self) -> None:
		"""JSCall with JSMember as argument."""
		cn = Import("cn", "clsx")
		styles = Import("styles", "./styles.module.css")
		call = cn(styles.container, styles.active)
		result = call.emit()
		assert (
			f"cn_{cn.id}(styles_{styles.id}.container, styles_{styles.id}.active)"
			== result
		)


class TestToJsExpr:
	"""Tests for to_js_expr conversion function."""

	def test_string(self) -> None:
		"""String converts to JSString."""
		result = to_js_expr("hello")
		assert isinstance(result, JSString)
		# JSString uses double quotes
		assert result.emit() == '"hello"'

	def test_int(self) -> None:
		"""Int converts to JSNumber."""
		result = to_js_expr(42)
		assert isinstance(result, JSNumber)
		assert result.emit() == "42"

	def test_float(self) -> None:
		"""Float converts to JSNumber."""
		result = to_js_expr(3.14)
		assert isinstance(result, JSNumber)
		assert result.emit() == "3.14"

	def test_bool_true(self) -> None:
		"""True converts to JSBoolean."""
		result = to_js_expr(True)
		assert isinstance(result, JSBoolean)
		assert result.emit() == "true"

	def test_bool_false(self) -> None:
		"""False converts to JSBoolean."""
		result = to_js_expr(False)
		assert isinstance(result, JSBoolean)
		assert result.emit() == "false"

	def test_none(self) -> None:
		"""None converts to JSNull."""
		result = to_js_expr(None)
		assert isinstance(result, JSNull)
		assert result.emit() == "null"

	def test_list(self) -> None:
		"""List converts to JSArray."""
		result = to_js_expr([1, 2, 3])
		assert isinstance(result, JSArray)
		assert result.emit() == "[1, 2, 3]"

	def test_tuple(self) -> None:
		"""Tuple converts to JSArray."""
		result = to_js_expr((1, "a", True))
		assert isinstance(result, JSArray)
		# JSString uses double quotes
		assert result.emit() == '[1, "a", true]'

	def test_dict(self) -> None:
		"""Dict converts to JSObjectExpr."""
		result = to_js_expr({"a": 1, "b": "two"})
		assert isinstance(result, JSObjectExpr)
		# JSString uses double quotes
		assert result.emit() == '{"a": 1, "b": "two"}'

	def test_nested_structures(self) -> None:
		"""Nested structures convert correctly."""
		result = to_js_expr({"items": [1, 2], "nested": {"x": True}})
		assert isinstance(result, JSObjectExpr)
		# JSString uses double quotes
		assert result.emit() == '{"items": [1, 2], "nested": {"x": true}}'

	def test_jsexpr_passthrough(self) -> None:
		"""JSExpr values pass through unchanged."""
		original = JSString("hello")
		result = to_js_expr(original)
		assert result is original

	def test_import_passthrough(self) -> None:
		"""Import passes through unchanged (Import is a JSExpr)."""
		imp = Import("Button", "@mantine/core")
		result = to_js_expr(imp)
		assert result is imp  # Import is already a JSExpr, returns as-is
		assert result.emit() == f"Button_{imp.id}"

	def test_unsupported_type_raises(self) -> None:
		"""Unsupported types raise TypeError."""

		class CustomClass:
			pass

		with pytest.raises(TypeError, match="Cannot convert CustomClass"):
			to_js_expr(CustomClass())


class TestComplexExpressions:
	"""Tests for complex expression scenarios."""

	def test_method_call_on_import(self) -> None:
		"""Method call on import (chained member + call)."""
		React = Import.default("React", "react")
		# React.createElement("div")
		call = React.createElement("div")
		result = call.emit()
		assert f'React_{React.id}.createElement("div")' == result

	def test_method_call_interpreted(self) -> None:
		"""Method call in interpreted mode."""
		React = Import.default("React", "react")
		call = React.createElement("div")
		with interpreted_mode():
			result = call.emit()
		assert f"get_object('React_{React.id}').createElement(\"div\")" == result

	def test_cn_utility_pattern(self) -> None:
		"""Common cn() utility pattern works."""
		cn = Import("cn", "clsx")
		styles = Import("styles", "./app.module.css")

		# cn(styles.container, styles.active)
		call = cn(styles.container, styles.active)
		result = call.emit()
		assert (
			f"cn_{cn.id}(styles_{styles.id}.container, styles_{styles.id}.active)"
			== result
		)

	def test_cn_utility_interpreted(self) -> None:
		"""cn() pattern in interpreted mode."""
		cn = Import("cn", "clsx")
		styles = Import("styles", "./app.module.css")

		call = cn(styles.container)
		with interpreted_mode():
			result = call.emit()
		# Should wrap both cn and styles in get_object
		assert "get_object" in result


class TestImportRegistry:
	"""Tests for import registry deduplication."""

	def test_same_import_reuses_id(self) -> None:
		"""Same import definition reuses ID."""
		imp1 = Import("Button", "@mantine/core")
		imp2 = Import("Button", "@mantine/core")
		assert imp1.id == imp2.id

	def test_different_imports_get_different_ids(self) -> None:
		"""Different imports get different IDs."""
		imp1 = Import("Button", "@mantine/core")
		imp2 = Import("Input", "@mantine/core")
		assert imp1.id != imp2.id

	def test_type_only_merged_to_regular(self) -> None:
		"""Type-only import merged with regular becomes regular."""
		imp_type = Import("Foo", "./types", is_type_only=True)
		assert imp_type.is_type_only

		imp_regular = Import("Foo", "./types", is_type_only=False)
		# Both should now be regular (non-type-only)
		assert not imp_regular.is_type_only
		assert not imp_type.is_type_only

	def test_member_access_preserves_import_id(self) -> None:
		"""Member access via __getattr__ references the same Import ID."""
		styles = Import("styles", "./app.module.css")
		container = styles.container
		assert isinstance(container, JSMember)
		# The JSMember's base should reference the same import
		assert container.emit() == f"styles_{styles.id}.container"
