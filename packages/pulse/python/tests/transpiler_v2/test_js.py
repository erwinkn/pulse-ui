"""
Tests for JavaScript module bindings (pulse.js2) in transpiler_v2.

Tests verify that js2 modules transpile correctly to JavaScript code.
"""

# Import js2 modules at module level to ensure they're registered
import pulse.js2.array  # noqa: F401
import pulse.js2.array as ArrayModule
import pulse.js2.console  # noqa: F401

# Create module-level aliases for namespace imports (these resolve to JsModule ExprNodes)
import pulse.js2.console as console
import pulse.js2.date  # noqa: F401
import pulse.js2.date as DateModule
import pulse.js2.document  # noqa: F401
import pulse.js2.document as document
import pulse.js2.error  # noqa: F401
import pulse.js2.json  # noqa: F401
import pulse.js2.json as JSON
import pulse.js2.map  # noqa: F401
import pulse.js2.math  # noqa: F401
import pulse.js2.navigator  # noqa: F401
import pulse.js2.navigator as navigator
import pulse.js2.number  # noqa: F401
import pulse.js2.number as Number
import pulse.js2.object  # noqa: F401
import pulse.js2.object as ObjectModule
import pulse.js2.promise  # noqa: F401
import pulse.js2.promise as PromiseModule
import pulse.js2.regexp  # noqa: F401
import pulse.js2.set  # noqa: F401
import pulse.js2.string  # noqa: F401
import pulse.js2.string as StringModule
import pulse.js2.weakmap  # noqa: F401
import pulse.js2.weakset  # noqa: F401
import pulse.js2.window  # noqa: F401
import pulse.js2.window as window
import pytest
from pulse.js2 import Math
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# Math Module
# =============================================================================


class TestMath:
	def test_math_namespace_import(self):
		import pulse.js2.math as Math

		@javascript
		def get_pi():
			return Math.PI

		fn = get_pi.transpile()
		code = emit(fn)
		assert code == "function get_pi_1() {\nreturn Math.PI;\n}"

	def test_math_direct_import(self):
		# Use module-level Math import
		@javascript
		def round_down(x: float):
			return Math.floor(x)

		fn = round_down.transpile()
		code = emit(fn)
		assert code == "function round_down_1(x) {\nreturn Math.floor(x);\n}"

	def test_math_constants(self):
		# Use module-level Math import
		@javascript
		def get_constants():
			return Math.PI, Math.E, Math.SQRT2

		fn = get_constants.transpile()
		code = emit(fn)
		assert "Math.PI" in code
		assert "Math.E" in code
		assert "Math.SQRT2" in code

	def test_math_methods(self):
		# Use module-level Math import
		@javascript
		def calculate(x: float):
			return Math.sin(x) + Math.cos(x) + Math.sqrt(x) + Math.pow(x, 2)

		fn = calculate.transpile()
		code = emit(fn)
		assert "Math.sin(x)" in code
		assert "Math.cos(x)" in code
		assert "Math.sqrt(x)" in code
		assert "Math.pow(x, 2)" in code

	def test_math_from_js2_import(self):
		# Use module-level Math import
		@javascript
		def use_math(x: float):
			return Math.floor(x)

		fn = use_math.transpile()
		code = emit(fn)
		assert "Math.floor(x)" in code


# =============================================================================
# Console Module
# =============================================================================


class TestConsole:
	def test_console_namespace_import(self):
		# Use module-level console import
		@javascript
		def log_message(msg: str):
			console.log(msg)

		fn = log_message.transpile()
		code = emit(fn)
		assert code == "function log_message_1(msg) {\nreturn console.log(msg);\n}"

	def test_console_direct_import(self):
		# Use module-level console import
		@javascript
		def log_all(msg: str):
			console.log(msg)
			console.error(msg)
			console.warn(msg)

		fn = log_all.transpile()
		code = emit(fn)
		assert "console.log(msg)" in code
		assert "console.error(msg)" in code
		assert "console.warn(msg)" in code


# =============================================================================
# JSON Module
# =============================================================================


class TestJSON:
	def test_json_stringify(self):
		# Use module-level JSON import
		@javascript
		def to_json(obj: dict):
			return JSON.stringify(obj)

		fn = to_json.transpile()
		code = emit(fn)
		assert code == "function to_json_1(obj) {\nreturn JSON.stringify(obj);\n}"

	def test_json_parse(self):
		# Use module-level JSON import
		@javascript
		def from_json(s: str):
			return JSON.parse(s)

		fn = from_json.transpile()
		code = emit(fn)
		assert code == "function from_json_1(s) {\nreturn JSON.parse(s);\n}"

	def test_json_namespace(self):
		# Use module-level JSON import
		@javascript
		def round_trip(obj: dict):
			return JSON.parse(JSON.stringify(obj))

		fn = round_trip.transpile()
		code = emit(fn)
		assert "JSON.parse" in code
		assert "JSON.stringify" in code


# =============================================================================
# Number Module
# =============================================================================


class TestNumber:
	def test_number_static_methods(self):
		# Use module-level Number import
		@javascript
		def check_number(x: float):
			return Number.isFinite(x) and not Number.isNaN(x)

		fn = check_number.transpile()
		code = emit(fn)
		assert "Number.isFinite(x)" in code
		assert "Number.isNaN(x)" in code

	def test_number_constants(self):
		# Use module-level Number import
		@javascript
		def get_constants():
			return Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, Number.EPSILON

		fn = get_constants.transpile()
		code = emit(fn)
		assert "Number.MAX_SAFE_INTEGER" in code
		assert "Number.MIN_SAFE_INTEGER" in code
		assert "Number.EPSILON" in code

	def test_number_namespace(self):
		# Use module-level Number import
		@javascript
		def parse_int(s: str):
			return Number.parseInt(s, 10)

		fn = parse_int.transpile()
		code = emit(fn)
		assert code == "function parse_int_1(s) {\nreturn Number.parseInt(s, 10);\n}"


# =============================================================================
# String Module
# =============================================================================


class TestString:
	def test_string_from_char_code(self):
		# Use module-level StringModule import
		@javascript
		def make_string():
			return StringModule.fromCharCode(65, 66, 67)

		fn = make_string.transpile()
		code = emit(fn)
		assert "String.fromCharCode(65, 66, 67)" in code

	def test_string_constructor(self):
		from pulse.js2 import String

		@javascript
		def to_string(x):
			return String(x)

		fn = to_string.transpile()
		code = emit(fn)
		assert "new String(x)" in code


# =============================================================================
# Array Module
# =============================================================================


class TestArray:
	def test_array_constructor(self):
		from pulse.js2 import Array

		@javascript
		def make_array():
			return Array(1, 2, 3)

		fn = make_array.transpile()
		code = emit(fn)
		assert "new Array(1, 2, 3)" in code

	def test_array_static_methods(self):
		# Use module-level ArrayModule import
		@javascript
		def check_and_create(x):
			if ArrayModule.isArray(x):
				return ArrayModule.from_(x)

		fn = check_and_create.transpile()
		code = emit(fn)
		assert "Array.isArray(x)" in code
		assert "Array.from(x)" in code

	def test_array_from_js2_import(self):
		from pulse.js2 import Array

		@javascript
		def check_array(x):
			return Array.isArray(x)

		fn = check_array.transpile()
		code = emit(fn)
		assert "Array.isArray(x)" in code


# =============================================================================
# Set Module
# =============================================================================


class TestSet:
	def test_set_constructor_empty(self):
		from pulse.js2 import Set

		@javascript
		def make_set():
			return Set()

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1() {\nreturn new Set();\n}"

	def test_set_constructor_with_iterable(self):
		from pulse.js2 import Set

		@javascript
		def make_set(items: list):
			return Set(items)

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1(items) {\nreturn new Set(items);\n}"

	def test_set_methods(self):
		from pulse.js2 import Set

		@javascript
		def set_ops():
			s = Set([1, 2, 3])
			s.add(4)
			s.delete(1)
			return s.has(2)

		fn = set_ops.transpile()
		code = emit(fn)
		assert "new Set([1, 2, 3])" in code
		assert ".add(4)" in code
		assert ".delete(1)" in code
		assert ".has(2)" in code


# =============================================================================
# Map Module
# =============================================================================


class TestMap:
	def test_map_constructor_empty(self):
		from pulse.js2 import Map

		@javascript
		def make_map():
			return Map()

		fn = make_map.transpile()
		code = emit(fn)
		assert code == "function make_map_1() {\nreturn new Map();\n}"

	def test_map_constructor_with_iterable(self):
		from pulse.js2 import Map

		@javascript
		def make_map(pairs: list):
			return Map(pairs)

		fn = make_map.transpile()
		code = emit(fn)
		assert code == "function make_map_1(pairs) {\nreturn new Map(pairs);\n}"

	def test_map_methods(self):
		from pulse.js2 import Map

		@javascript
		def map_ops():
			m = Map([["a", 1], ["b", 2]])
			m.set("c", 3)
			return m.get("a")

		fn = map_ops.transpile()
		code = emit(fn)
		assert 'new Map([["a", 1], ["b", 2]])' in code
		assert '.set("c", 3)' in code
		assert '.get("a")' in code


# =============================================================================
# Date Module
# =============================================================================


class TestDate:
	def test_date_constructor(self):
		from pulse.js2 import Date

		@javascript
		def make_date():
			return Date()

		fn = make_date.transpile()
		code = emit(fn)
		assert code == "function make_date_1() {\nreturn new Date();\n}"

	def test_date_static_methods(self):
		# Use module-level DateModule import
		@javascript
		def get_timestamp():
			return DateModule.now()

		fn = get_timestamp.transpile()
		code = emit(fn)
		assert code == "function get_timestamp_1() {\nreturn Date.now();\n}"

	def test_date_methods(self):
		from pulse.js2 import Date

		@javascript
		def date_ops():
			d = Date()
			return d.getTime(), d.getFullYear()

		fn = date_ops.transpile()
		code = emit(fn)
		assert "new Date()" in code
		assert ".getTime()" in code
		assert ".getFullYear()" in code


# =============================================================================
# Promise Module
# =============================================================================


class TestPromise:
	def test_promise_constructor(self):
		from pulse.js2 import Promise

		@javascript
		def make_promise():
			return Promise(lambda resolve, reject: resolve(42))

		fn = make_promise.transpile()
		code = emit(fn)
		assert "new Promise" in code

	def test_promise_static_methods(self):
		# Use module-level PromiseModule import
		@javascript
		def promise_ops():
			return PromiseModule.resolve(42), PromiseModule.reject("error")

		fn = promise_ops.transpile()
		code = emit(fn)
		assert "Promise.resolve(42)" in code
		assert 'Promise.reject("error")' in code

	def test_promise_methods(self):
		from pulse.js2 import Promise

		@javascript
		def promise_chain():
			p = Promise.resolve(1)
			return p.then(lambda x: x + 1)

		fn = promise_chain.transpile()
		code = emit(fn)
		assert "Promise.resolve(1)" in code
		assert ".then" in code


# =============================================================================
# Error Module
# =============================================================================


class TestError:
	def test_error_constructor(self):
		from pulse.js2 import Error

		@javascript
		def make_error(msg: str):
			return Error(msg)

		fn = make_error.transpile()
		code = emit(fn)
		assert code == "function make_error_1(msg) {\nreturn new Error(msg);\n}"

	def test_error_subclasses(self):
		from pulse.js2.error import RangeError, ReferenceError, TypeError

		@javascript
		def make_errors():
			return TypeError("type"), RangeError("range"), ReferenceError("ref")

		fn = make_errors.transpile()
		code = emit(fn)
		assert 'new TypeError("type")' in code
		assert 'new RangeError("range")' in code
		assert 'new ReferenceError("ref")' in code


# =============================================================================
# RegExp Module
# =============================================================================


class TestRegExp:
	def test_regexp_constructor(self):
		from pulse.js2 import RegExp

		@javascript
		def make_regexp(pattern: str):
			return RegExp(pattern, "g")

		fn = make_regexp.transpile()
		code = emit(fn)
		assert (
			code
			== 'function make_regexp_1(pattern) {\nreturn new RegExp(pattern, "g");\n}'
		)

	def test_regexp_methods(self):
		from pulse.js2 import RegExp

		@javascript
		def regexp_ops(pattern: str, text: str):
			re = RegExp(pattern)
			return re.test(text), re.exec(text)

		fn = regexp_ops.transpile()
		code = emit(fn)
		assert "new RegExp(pattern)" in code
		assert ".test(text)" in code
		assert ".exec(text)" in code


# =============================================================================
# Object Module
# =============================================================================


class TestObject:
	def test_object_static_methods(self):
		# Use module-level ObjectModule import
		@javascript
		def object_ops(obj: dict):
			return (
				ObjectModule.keys(obj),
				ObjectModule.values(obj),
				ObjectModule.entries(obj),
			)

		fn = object_ops.transpile()
		code = emit(fn)
		assert "Object.keys(obj)" in code
		assert "Object.values(obj)" in code
		assert "Object.entries(obj)" in code

	def test_object_assign(self):
		# Use module-level ObjectModule import
		@javascript
		def merge_objects(target: dict, source: dict):
			return ObjectModule.assign(target, source)

		fn = merge_objects.transpile()
		code = emit(fn)
		assert "Object.assign(target, source)" in code

	def test_object_is(self):
		# Use module-level ObjectModule import
		@javascript
		def same_value(a, b):
			return ObjectModule.is_(a, b)

		fn = same_value.transpile()
		code = emit(fn)
		assert "Object.is(a, b)" in code


# =============================================================================
# WeakMap Module
# =============================================================================


class TestWeakMap:
	def test_weakmap_constructor(self):
		from pulse.js2 import WeakMap

		@javascript
		def make_weakmap():
			return WeakMap()

		fn = make_weakmap.transpile()
		code = emit(fn)
		assert code == "function make_weakmap_1() {\nreturn new WeakMap();\n}"

	def test_weakmap_methods(self):
		from pulse.js2 import WeakMap

		@javascript
		def weakmap_ops(key, value):
			wm = WeakMap()
			wm.set(key, value)
			return wm.get(key), wm.has(key)

		fn = weakmap_ops.transpile()
		code = emit(fn)
		assert "new WeakMap()" in code
		assert ".set(key, value)" in code
		assert ".get(key)" in code
		assert ".has(key)" in code


# =============================================================================
# WeakSet Module
# =============================================================================


class TestWeakSet:
	def test_weakset_constructor(self):
		from pulse.js2 import WeakSet

		@javascript
		def make_weakset():
			return WeakSet()

		fn = make_weakset.transpile()
		code = emit(fn)
		assert code == "function make_weakset_1() {\nreturn new WeakSet();\n}"

	def test_weakset_methods(self):
		from pulse.js2 import WeakSet

		@javascript
		def weakset_ops(value):
			ws = WeakSet()
			ws.add(value)
			return ws.has(value), ws.delete(value)

		fn = weakset_ops.transpile()
		code = emit(fn)
		assert "new WeakSet()" in code
		assert ".add(value)" in code
		assert ".has(value)" in code
		assert ".delete(value)" in code


# =============================================================================
# Window Module
# =============================================================================


class TestWindow:
	def test_window_properties(self):
		from pulse.js2 import window

		@javascript
		def get_dimensions():
			return window.innerWidth, window.innerHeight

		fn = get_dimensions.transpile()
		code = emit(fn)
		assert "window.innerWidth" in code
		assert "window.innerHeight" in code

	def test_window_methods(self):
		# Use module-level window import
		@javascript
		def window_ops(msg: str):
			window.alert(msg)
			window.setTimeout(lambda: None, 1000)

		fn = window_ops.transpile()
		code = emit(fn)
		assert "window.alert(msg)" in code
		assert "window.setTimeout" in code


# =============================================================================
# Document Module
# =============================================================================


class TestDocument:
	def test_document_query_methods(self):
		# Use module-level document import
		@javascript
		def query_elements(selector: str):
			return document.querySelector(selector), document.querySelectorAll(selector)

		fn = query_elements.transpile()
		code = emit(fn)
		assert "document.querySelector(selector)" in code
		assert "document.querySelectorAll(selector)" in code

	def test_document_create_methods(self):
		# Use module-level document import
		@javascript
		def create_elements():
			return document.createElement("div"), document.createTextNode("text")

		fn = create_elements.transpile()
		code = emit(fn)
		assert 'document.createElement("div")' in code
		assert 'document.createTextNode("text")' in code


# =============================================================================
# Navigator Module
# =============================================================================


class TestNavigator:
	def test_navigator_properties(self):
		from pulse.js2 import navigator

		@javascript
		def get_info():
			return navigator.userAgent, navigator.language, navigator.onLine

		fn = get_info.transpile()
		code = emit(fn)
		assert "navigator.userAgent" in code
		assert "navigator.language" in code
		assert "navigator.onLine" in code

	def test_navigator_methods(self):
		# Use module-level navigator import
		@javascript
		def navigator_ops():
			navigator.vibrate([100, 50, 100])
			return navigator.canShare({"title": "test"})

		fn = navigator_ops.transpile()
		code = emit(fn)
		assert "navigator.vibrate" in code
		assert "navigator.canShare" in code


# =============================================================================
# Direct Imports from pulse.js2
# =============================================================================


class TestDirectImports:
	def test_direct_import_set(self):
		from pulse.js2 import Set

		@javascript
		def make_set():
			return Set([1, 2, 3])

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1() {\nreturn new Set([1, 2, 3]);\n}"

	def test_direct_import_array(self):
		from pulse.js2 import Array

		@javascript
		def make_array():
			return Array(1, 2, 3)

		fn = make_array.transpile()
		code = emit(fn)
		assert "new Array(1, 2, 3)" in code

	def test_direct_import_math(self):
		from pulse.js2 import Math

		@javascript
		def use_math(x: float):
			return Math.floor(x)

		fn = use_math.transpile()
		code = emit(fn)
		assert "Math.floor(x)" in code

	def test_direct_import_console(self):
		# Use module-level console import
		@javascript
		def log(msg: str):
			console.log(msg)

		fn = log.transpile()
		code = emit(fn)
		assert "console.log(msg)" in code

	def test_direct_import_promise(self):
		from pulse.js2 import Promise

		@javascript
		def make_promise():
			return Promise.resolve(42)

		fn = make_promise.transpile()
		code = emit(fn)
		assert "Promise.resolve(42)" in code


# =============================================================================
# Undefined
# =============================================================================


class TestUndefined:
	def test_undefined(self):
		from pulse.js2 import undefined

		@javascript
		def return_undefined():
			return undefined

		fn = return_undefined.transpile()
		code = emit(fn)
		assert code == "function return_undefined_1() {\nreturn undefined;\n}"
