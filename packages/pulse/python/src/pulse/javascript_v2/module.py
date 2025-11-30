from types import ModuleType


class JsModule: ...


class PyModule: ...


PY_MODULES: dict[ModuleType, type[PyModule]] = {}


def register_module(module: ModuleType, transpilation: type[PyModule]):
	PY_MODULES[module] = transpilation
