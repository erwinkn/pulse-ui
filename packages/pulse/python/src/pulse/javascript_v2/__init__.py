from pulse.javascript_v2.codegen import (
	CodegenOutput,
	ConstantDef,
	FunctionDef,
	collect_from_functions,
	collect_from_registries,
)
from pulse.javascript_v2.constants import CONSTANTS_CACHE
from pulse.javascript_v2.function import FUNCTION_CACHE, JsFunction
from pulse.javascript_v2.imports import (
	IMPORT_REGISTRY,
	Import,
	clear_import_registry,
	js_import,
)


def clear_registries() -> None:
	"""Clear all registries. Useful for testing."""

	clear_import_registry()
	FUNCTION_CACHE.clear()
	CONSTANTS_CACHE.clear()


__all__ = [
	# Core types
	"JsFunction",
	"Import",
	"js_import",
	# Codegen output
	"CodegenOutput",
	"ConstantDef",
	"FunctionDef",
	"collect_from_functions",
	"collect_from_registries",
	# Registry management
	"IMPORT_REGISTRY",
	"clear_registries",
]
