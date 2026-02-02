"""
Tests for JavaScript module bindings (pulse.js) in transpiler.

Tests verify that js2 modules transpile correctly to JavaScript code.
"""

from __future__ import annotations

from typing import Any

# Namespace imports for function-only modules (correct pattern)
import pulse.js.console as console
import pulse.js.document as document
import pulse.js.json as JSON
import pulse.js.navigator as navigator
import pulse.js.window as window
import pytest

# Class imports (correct pattern - import the class, not the module)
from pulse.js import (
	URL,
	AbortController,
	Animation,
	Array,
	ArrayBuffer,
	Blob,
	CustomEvent,
	Date,
	DocumentTimeline,
	DOMParser,
	Error,
	File,
	FileReader,
	FormData,
	Headers,
	IntersectionObserver,
	Intl,
	KeyframeEffect,
	Map,
	Math,
	MutationObserver,
	Number,
	Object,
	PerformanceObserver,
	Promise,
	RegExp,
	Request,
	ResizeObserver,
	Response,
	Set,
	String,
	TextDecoder,
	TextEncoder,
	Uint8Array,
	URLSearchParams,
	WeakMap,
	WeakSet,
	XMLSerializer,
	crypto,
	fetch,
	obj,
	undefined,
)
from pulse.transpiler import (
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
		import pulse.js.math as Math

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
		assert (
			code
			== "function get_constants_1() {\nreturn [Math.PI, Math.E, Math.SQRT2];\n}"
		)

	def test_math_methods(self):
		# Use module-level Math import
		@javascript
		def calculate(x: float):
			return Math.sin(x) + Math.cos(x) + Math.sqrt(x) + Math.pow(x, 2)

		fn = calculate.transpile()
		code = emit(fn)
		assert (
			code
			== "function calculate_1(x) {\nreturn Math.sin(x) + Math.cos(x) + Math.sqrt(x) + Math.pow(x, 2);\n}"
		)

	def test_math_from_js2_import(self):
		# Use module-level Math import
		@javascript
		def use_math(x: float):
			return Math.floor(x)

		fn = use_math.transpile()
		code = emit(fn)
		assert code == "function use_math_1(x) {\nreturn Math.floor(x);\n}"


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
		assert (
			code
			== "function log_all_1(msg) {\nconsole.log(msg);\nconsole.error(msg);\nconsole.warn(msg);\n}"
		)


# =============================================================================
# JSON Module
# =============================================================================


class TestJSON:
	def test_json_stringify(self):
		# Use module-level JSON import
		@javascript
		def to_json(obj: dict[str, Any]):
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
		def round_trip(obj: dict[str, Any]):
			return JSON.parse(JSON.stringify(obj))

		fn = round_trip.transpile()
		code = emit(fn)
		assert (
			code
			== "function round_trip_1(obj) {\nreturn JSON.parse(JSON.stringify(obj));\n}"
		)


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
		assert (
			code
			== "function check_number_1(x) {\nreturn Number.isFinite(x) && !Number.isNaN(x);\n}"
		)

	def test_number_constants(self):
		# Use module-level Number import
		@javascript
		def get_constants():
			return Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, Number.EPSILON

		fn = get_constants.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_constants_1() {\nreturn [Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, Number.EPSILON];\n}"
		)

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
		@javascript
		def make_string():
			return String.fromCharCode(65, 66, 67)

		fn = make_string.transpile()
		code = emit(fn)
		assert (
			code
			== "function make_string_1() {\nreturn String.fromCharCode(65, 66, 67);\n}"
		)

	def test_string_constructor(self):
		@javascript
		def to_string(x: int):
			return String(x)

		fn = to_string.transpile()
		code = emit(fn)
		assert code == "function to_string_1(x) {\nreturn new String(x);\n}"


# =============================================================================
# Array Module
# =============================================================================


class TestArray:
	def test_array_constructor(self):
		@javascript
		def make_array():
			return Array(1, 2, 3)

		fn = make_array.transpile()
		code = emit(fn)
		assert code == "function make_array_1() {\nreturn new Array(1, 2, 3);\n}"

	def test_array_static_methods(self):
		@javascript
		def check_and_create(x: list[int]):
			if Array.isArray(x):
				return Array.from_(x)

		fn = check_and_create.transpile()
		code = emit(fn)
		assert (
			code
			== "function check_and_create_1(x) {\nif (Array.isArray(x)) {\nreturn Array.from(x);\n}\n}"
		)

	def test_array_from_js2_import(self):
		@javascript
		def check_array(x: Any) -> bool:
			return Array.isArray(x)

		fn = check_array.transpile()
		code = emit(fn)
		assert code == "function check_array_1(x) {\nreturn Array.isArray(x);\n}"


# =============================================================================
# Set Module
# =============================================================================


class TestSet:
	def test_set_constructor_empty(self):
		@javascript
		def make_set() -> Set[int]:
			return Set()

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1() {\nreturn new Set();\n}"

	def test_set_constructor_with_iterable(self):
		@javascript
		def make_set(items: list[int]):
			return Set(items)

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1(items) {\nreturn new Set(items);\n}"

	def test_set_methods(self):
		@javascript
		def set_ops():
			s = Set([1, 2, 3])
			s.add(4)
			s.delete(1)
			return s.has(2)

		fn = set_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function set_ops_1() {\nlet s;\ns = new Set([1, 2, 3]);\ns.add(4);\ns.delete(1);\nreturn s.has(2);\n}"
		)


# =============================================================================
# Map Module
# =============================================================================


class TestMap:
	def test_map_constructor_empty(self):
		@javascript
		def make_map() -> Map[str, int]:
			return Map()

		fn = make_map.transpile()
		code = emit(fn)
		assert code == "function make_map_1() {\nreturn new Map();\n}"

	def test_map_constructor_with_iterable(self):
		@javascript
		def make_map(pairs: list[tuple[str, int]]):
			return Map(pairs)

		fn = make_map.transpile()
		code = emit(fn)
		assert code == "function make_map_1(pairs) {\nreturn new Map(pairs);\n}"

	def test_map_methods(self):
		@javascript
		def map_ops():
			m: Map[str, int] = Map([("a", 1), ("b", 2)])
			m.set("c", 3)
			return m.get("a")

		fn = map_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function map_ops_1() {\nlet m;\nm = new Map([["a", 1], ["b", 2]]);\nm.set("c", 3);\nreturn m.get("a");\n}'
		)


# =============================================================================
# Date Module
# =============================================================================


class TestDate:
	def test_date_constructor(self):
		@javascript
		def make_date():
			return Date()

		fn = make_date.transpile()
		code = emit(fn)
		assert code == "function make_date_1() {\nreturn new Date();\n}"

	def test_date_static_methods(self):
		@javascript
		def get_timestamp():
			return Date.now()

		fn = get_timestamp.transpile()
		code = emit(fn)
		assert code == "function get_timestamp_1() {\nreturn Date.now();\n}"

	def test_date_methods(self):
		@javascript
		def date_ops():
			d = Date()
			return d.getTime(), d.getFullYear()

		fn = date_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function date_ops_1() {\nlet d;\nd = new Date();\nreturn [d.getTime(), d.getFullYear()];\n}"
		)


# =============================================================================
# Promise Module
# =============================================================================


class TestPromise:
	def test_promise_constructor(self):
		@javascript
		def make_promise():
			return Promise(lambda resolve, reject: resolve(42))

		fn = make_promise.transpile()
		code = emit(fn)
		assert (
			code
			== "function make_promise_1() {\nreturn new Promise((resolve, reject) => resolve(42));\n}"
		)

	def test_promise_static_methods(self):
		@javascript
		def promise_ops():
			return Promise.resolve(42), Promise.reject("error")

		fn = promise_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function promise_ops_1() {\nreturn [Promise.resolve(42), Promise.reject("error")];\n}'
		)

	def test_promise_methods(self):
		@javascript
		def promise_chain():
			p = Promise.resolve(1)
			return p.then(lambda x: x + 1)

		fn = promise_chain.transpile()
		code = emit(fn)
		assert (
			code
			== "function promise_chain_1() {\nlet p;\np = Promise.resolve(1);\nreturn p.then(x => x + 1);\n}"
		)


# =============================================================================
# URL Module
# =============================================================================


class TestURL:
	def test_url_search_params(self):
		@javascript
		def url_ops():
			url = URL("https://example.com?foo=1")
			params = URLSearchParams(url.search)
			params.append("bar", "2")
			return url.href, params.toString()

		fn = url_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function url_ops_1() {\nlet params, url;\nurl = new URL("https://example.com?foo=1");\nparams = new URLSearchParams(url.search);\nparams.append("bar", "2");\nreturn [url.href, params.toString()];\n}'
		)


# =============================================================================
# AbortController Module
# =============================================================================


class TestAbortController:
	def test_abort_controller(self):
		@javascript
		def abort_ops():
			controller = AbortController()
			controller.abort()
			return controller.signal.aborted

		fn = abort_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function abort_ops_1() {\nlet controller;\ncontroller = new AbortController();\ncontroller.abort();\nreturn controller.signal.aborted;\n}"
		)


# =============================================================================
# Fetch Module
# =============================================================================


class TestFetch:
	def test_fetch_request(self):
		@javascript
		def fetch_ops():
			headers = Headers()
			headers.set("Content-Type", "application/json")
			req = Request(
				"/api",
				obj(method="POST", headers=headers, body="{}"),
			)
			return fetch(req)

		fn = fetch_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function fetch_ops_1() {\nlet headers, req;\nheaders = new Headers();\nheaders.set("Content-Type", "application/json");\nreq = new Request("/api", {"method": "POST", "headers": headers, "body": "{}"});\nreturn fetch(req);\n}'
		)

	def test_response_constructor(self):
		@javascript
		def response_ops():
			res = Response("ok", obj(status=200))
			return res.ok, res.status

		fn = response_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function response_ops_1() {\nlet res;\nres = new Response("ok", {"status": 200});\nreturn [res.ok, res.status];\n}'
		)


# =============================================================================
# FormData Module
# =============================================================================


class TestFormData:
	def test_form_data_basic(self):
		@javascript
		def form_ops():
			form = FormData()
			form.append("name", "Ada")
			return form.get("name")

		fn = form_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function form_ops_1() {\nlet form;\nform = new FormData();\nform.append("name", "Ada");\nreturn form.get("name");\n}'
		)


# =============================================================================
# Blob/File/FileReader Modules
# =============================================================================


class TestBlobFile:
	def test_blob_basic(self):
		@javascript
		def blob_ops():
			blob = Blob(["hi"], obj(type="text/plain"))
			return blob.type

		fn = blob_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function blob_ops_1() {\nlet blob;\nblob = new Blob(["hi"], {"type": "text/plain"});\nreturn blob.type;\n}'
		)

	def test_file_basic(self):
		@javascript
		def file_ops():
			file = File(["hi"], "note.txt", obj(type="text/plain"))
			return file.name

		fn = file_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function file_ops_1() {\nlet file;\nfile = new File(["hi"], "note.txt", {"type": "text/plain"});\nreturn file.name;\n}'
		)

	def test_file_reader_basic(self):
		@javascript
		def reader_ops(blob):
			reader = FileReader()
			reader.readAsText(blob)
			return reader.result

		fn = reader_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function reader_ops_1(blob) {\nlet reader;\nreader = new FileReader();\nreader.readAsText(blob);\nreturn reader.result;\n}"
		)


# =============================================================================
# TextEncoder/TextDecoder Modules
# =============================================================================


class TestTextEncoding:
	def test_text_encoding(self):
		@javascript
		def text_ops(text: str):
			encoder = TextEncoder()
			data = encoder.encode(text)
			decoder = TextDecoder("utf-8")
			return decoder.decode(data)

		fn = text_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function text_ops_1(text) {\nlet data, decoder, encoder;\nencoder = new TextEncoder();\ndata = encoder.encode(text);\ndecoder = new TextDecoder("utf-8");\nreturn decoder.decode(data);\n}'
		)


# =============================================================================
# ArrayBuffer/TypedArray Modules
# =============================================================================


class TestArrayBuffer:
	def test_array_buffer_basic(self):
		@javascript
		def buffer_ops():
			buf = ArrayBuffer(8)
			view = Uint8Array(buf)
			return buf.byteLength, view.byteLength

		fn = buffer_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function buffer_ops_1() {\nlet buf, view;\nbuf = new ArrayBuffer(8);\nview = new Uint8Array(buf);\nreturn [buf.byteLength, view.byteLength];\n}"
		)


# =============================================================================
# Observer Modules
# =============================================================================


class TestIntersectionObserver:
	def test_intersection_observer(self):
		@javascript
		def intersection_ops(target):
			observer = IntersectionObserver(
				lambda entries, obs: None,
				obj(threshold=0.5),
			)
			observer.observe(target)
			observer.disconnect()
			return observer.takeRecords()

		fn = intersection_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function intersection_ops_1(target) {\nlet observer;\nobserver = new IntersectionObserver((entries, obs) => null, {"threshold": 0.5});\nobserver.observe(target);\nobserver.disconnect();\nreturn observer.takeRecords();\n}'
		)


class TestResizeObserver:
	def test_resize_observer(self):
		@javascript
		def resize_ops(target):
			observer = ResizeObserver(lambda entries, obs: None)
			observer.observe(target, obj(box="border-box"))
			observer.unobserve(target)
			return observer.disconnect()

		fn = resize_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function resize_ops_1(target) {\nlet observer;\nobserver = new ResizeObserver((entries, obs) => null);\nobserver.observe(target, {"box": "border-box"});\nobserver.unobserve(target);\nreturn observer.disconnect();\n}'
		)


class TestPerformanceObserver:
	def test_performance_observer(self):
		@javascript
		def perf_ops():
			observer = PerformanceObserver(lambda list_, obs: None)
			observer.observe(obj(entryTypes=["mark", "measure"]))
			return observer.takeRecords()

		fn = perf_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function perf_ops_1() {\nlet observer;\nobserver = new PerformanceObserver((list_, obs) => null);\nobserver.observe({"entryTypes": ["mark", "measure"]});\nreturn observer.takeRecords();\n}'
		)


# =============================================================================
# Web Animations API
# =============================================================================


class TestWebAnimations:
	def test_keyframe_effect_animation(self):
		@javascript
		def animate(target):
			effect = KeyframeEffect(
				target,
				[obj(opacity=0), obj(opacity=1)],
				obj(duration=300, easing="ease-in-out"),
			)
			animation = Animation(effect, document.timeline)
			animation.play()
			return animation.playState

		fn = animate.transpile()
		code = emit(fn)
		assert (
			code
			== 'function animate_1(target) {\nlet animation, effect;\neffect = new KeyframeEffect(target, [{"opacity": 0}, {"opacity": 1}], {"duration": 300, "easing": "ease-in-out"});\nanimation = new Animation(effect, document.timeline);\nanimation.play();\nreturn animation.playState;\n}'
		)

	def test_document_timeline(self):
		@javascript
		def timeline_ops():
			timeline = DocumentTimeline(obj(originTime=0))
			return timeline.currentTime

		fn = timeline_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function timeline_ops_1() {\nlet timeline;\ntimeline = new DocumentTimeline({"originTime": 0});\nreturn timeline.currentTime;\n}'
		)


# =============================================================================
# DOMParser/XMLSerializer Module
# =============================================================================


class TestDomParser:
	def test_dom_parser(self):
		@javascript
		def dom_ops(source: str):
			parser = DOMParser()
			doc = parser.parseFromString(source, "text/html")
			serializer = XMLSerializer()
			return serializer.serializeToString(doc)

		fn = dom_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function dom_ops_1(source) {\nlet doc, parser, serializer;\nparser = new DOMParser();\ndoc = parser.parseFromString(source, "text/html");\nserializer = new XMLSerializer();\nreturn serializer.serializeToString(doc);\n}'
		)


# =============================================================================
# CustomEvent Module
# =============================================================================


class TestCustomEvent:
	def test_custom_event(self):
		@javascript
		def custom_event_ops():
			event = CustomEvent("ping", obj(detail=obj(ok=True)))
			return event.detail

		fn = custom_event_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function custom_event_ops_1() {\nlet event;\nevent = new CustomEvent("ping", {"detail": {"ok": true}});\nreturn event.detail;\n}'
		)


# =============================================================================
# Intl/Crypto Modules
# =============================================================================


class TestIntlCrypto:
	def test_intl_number_format(self):
		@javascript
		def intl_ops(value: float):
			fmt = Intl.NumberFormat("en-US")
			return fmt.format(value)

		fn = intl_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function intl_ops_1(value) {\nlet fmt;\nfmt = new Intl.NumberFormat("en-US");\nreturn fmt.format(value);\n}'
		)

	def test_crypto_random(self):
		@javascript
		def crypto_ops():
			buf = Uint8Array(16)
			crypto.getRandomValues(buf)
			return crypto.randomUUID()

		fn = crypto_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function crypto_ops_1() {\nlet buf;\nbuf = new Uint8Array(16);\ncrypto.getRandomValues(buf);\nreturn crypto.randomUUID();\n}"
		)


# =============================================================================
# MutationObserver Module
# =============================================================================


class TestMutationObserver:
	def test_mutation_observer_constructor(self):
		@javascript
		def make_observer():
			return MutationObserver(lambda records, observer: None)

		fn = make_observer.transpile()
		code = emit(fn)
		assert (
			code
			== "function make_observer_1() {\nreturn new MutationObserver((records, observer) => null);\n}"
		)

	def test_mutation_observer_methods(self):
		@javascript
		def observer_ops(target):
			observer = MutationObserver(lambda records, obs: None)
			observer.observe(target, obj(childList=True, subtree=True))
			observer.disconnect()
			return observer.takeRecords()

		fn = observer_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function observer_ops_1(target) {\nlet observer;\nobserver = new MutationObserver((records, obs) => null);\nobserver.observe(target, {"childList": true, "subtree": true});\nobserver.disconnect();\nreturn observer.takeRecords();\n}'
		)


# =============================================================================
# Error Module
# =============================================================================


class TestError:
	def test_error_constructor(self):
		@javascript
		def make_error(msg: str):
			return Error(msg)

		fn = make_error.transpile()
		code = emit(fn)
		assert code == "function make_error_1(msg) {\nreturn new Error(msg);\n}"

	def test_error_subclasses(self):
		from pulse.js.error import RangeError, ReferenceError, TypeError

		@javascript
		def make_errors():
			return TypeError("type"), RangeError("range"), ReferenceError("ref")

		fn = make_errors.transpile()
		code = emit(fn)
		assert (
			code
			== 'function make_errors_1() {\nreturn [new TypeError("type"), new RangeError("range"), new ReferenceError("ref")];\n}'
		)


# =============================================================================
# RegExp Module
# =============================================================================


class TestRegExp:
	def test_regexp_constructor(self):
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
		@javascript
		def regexp_ops(pattern: str, text: str):
			re = RegExp(pattern)
			return re.test(text), re.exec(text)

		fn = regexp_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function regexp_ops_1(pattern, text) {\nlet re;\nre = new RegExp(pattern);\nreturn [re.test(text), re.exec(text)];\n}"
		)


# =============================================================================
# Object Module
# =============================================================================


class TestObject:
	def test_object_static_methods(self):
		@javascript
		def object_ops(obj: dict[str, Any]):
			return (
				Object.keys(obj),
				Object.values(obj),
				Object.entries(obj),
			)

		fn = object_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function object_ops_1(obj) {\nreturn [Object.keys(obj), Object.values(obj), Object.entries(obj)];\n}"
		)

	def test_object_assign(self):
		@javascript
		def merge_objects(target: dict[str, Any], source: dict[str, Any]):
			return Object.assign(target, source)

		fn = merge_objects.transpile()
		code = emit(fn)
		assert (
			code
			== "function merge_objects_1(target, source) {\nreturn Object.assign(target, source);\n}"
		)

	def test_object_is(self):
		@javascript
		def same_value(a: object, b: object):
			return Object.is_(a, b)

		fn = same_value.transpile()
		code = emit(fn)
		assert code == "function same_value_1(a, b) {\nreturn Object.is(a, b);\n}"


# =============================================================================
# WeakMap Module
# =============================================================================


class TestWeakMap:
	def test_weakmap_constructor(self):
		@javascript
		def make_weakmap() -> WeakMap[object, int]:
			return WeakMap()

		fn = make_weakmap.transpile()
		code = emit(fn)
		assert code == "function make_weakmap_1() {\nreturn new WeakMap();\n}"

	def test_weakmap_methods(self):
		@javascript
		def weakmap_ops(key: str, value: int):
			wm: WeakMap[str, int] = WeakMap()
			wm.set(key, value)
			return wm.get(key), wm.has(key)

		fn = weakmap_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function weakmap_ops_1(key, value) {\nlet wm;\nwm = new WeakMap();\nwm.set(key, value);\nreturn [wm.get(key), wm.has(key)];\n}"
		)


# =============================================================================
# WeakSet Module
# =============================================================================


class TestWeakSet:
	def test_weakset_constructor(self):
		@javascript
		def make_weakset() -> WeakSet[object]:
			return WeakSet()

		fn = make_weakset.transpile()
		code = emit(fn)
		assert code == "function make_weakset_1() {\nreturn new WeakSet();\n}"

	def test_weakset_methods(self):
		@javascript
		def weakset_ops(value: object):
			ws: WeakSet[object] = WeakSet()
			ws.add(value)
			return ws.has(value), ws.delete(value)

		fn = weakset_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function weakset_ops_1(value) {\nlet ws;\nws = new WeakSet();\nws.add(value);\nreturn [ws.has(value), ws.delete(value)];\n}"
		)


# =============================================================================
# Window Module
# =============================================================================


class TestWindow:
	def test_window_properties(self):
		@javascript
		def get_dimensions():
			return window.innerWidth, window.innerHeight

		fn = get_dimensions.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_dimensions_1() {\nreturn [window.innerWidth, window.innerHeight];\n}"
		)

	def test_window_methods(self):
		# Use module-level window import
		@javascript
		def window_ops(msg: str):
			window.alert(msg)
			window.setTimeout(lambda: None, 1000)

		fn = window_ops.transpile()
		code = emit(fn)
		assert (
			code
			== "function window_ops_1(msg) {\nwindow.alert(msg);\nwindow.setTimeout(() => null, 1000);\n}"
		)


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
		assert (
			code
			== "function query_elements_1(selector) {\nreturn [document.querySelector(selector), document.querySelectorAll(selector)];\n}"
		)

	def test_document_create_methods(self):
		# Use module-level document import
		@javascript
		def create_elements():
			return document.createElement("div"), document.createTextNode("text")

		fn = create_elements.transpile()
		code = emit(fn)
		assert (
			code
			== 'function create_elements_1() {\nreturn [document.createElement("div"), document.createTextNode("text")];\n}'
		)


# =============================================================================
# Navigator Module
# =============================================================================


class TestNavigator:
	def test_navigator_properties(self):
		@javascript
		def get_info():
			return navigator.userAgent, navigator.language, navigator.onLine

		fn = get_info.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_info_1() {\nreturn [navigator.userAgent, navigator.language, navigator.onLine];\n}"
		)

	def test_navigator_methods(self):
		# Use module-level navigator import
		@javascript
		def navigator_ops():
			navigator.vibrate([100, 50, 100])
			return navigator.canShare({"title": "test"})

		fn = navigator_ops.transpile()
		code = emit(fn)
		assert (
			code
			== 'function navigator_ops_1() {\nnavigator.vibrate([100, 50, 100]);\nreturn navigator.canShare(new Map([["title", "test"]]));\n}'
		)


# =============================================================================
# Direct Imports from pulse.js
# =============================================================================


class TestDirectImports:
	def test_direct_import_set(self):
		@javascript
		def make_set():
			return Set([1, 2, 3])

		fn = make_set.transpile()
		code = emit(fn)
		assert code == "function make_set_1() {\nreturn new Set([1, 2, 3]);\n}"

	def test_direct_import_array(self):
		@javascript
		def make_array():
			return Array(1, 2, 3)

		fn = make_array.transpile()
		code = emit(fn)
		assert code == "function make_array_1() {\nreturn new Array(1, 2, 3);\n}"

	def test_direct_import_math(self):
		@javascript
		def use_math(x: float):
			return Math.floor(x)

		fn = use_math.transpile()
		code = emit(fn)
		assert code == "function use_math_1(x) {\nreturn Math.floor(x);\n}"

	def test_direct_import_console(self):
		@javascript
		def log(msg: str):
			console.log(msg)

		fn = log.transpile()
		code = emit(fn)
		assert code == "function log_1(msg) {\nreturn console.log(msg);\n}"

	def test_direct_import_promise(self):
		@javascript
		def make_promise():
			return Promise.resolve(42)

		fn = make_promise.transpile()
		code = emit(fn)
		assert code == "function make_promise_1() {\nreturn Promise.resolve(42);\n}"


# =============================================================================
# Undefined
# =============================================================================


class TestUndefined:
	def test_undefined(self):
		@javascript
		def return_undefined():
			return undefined

		fn = return_undefined.transpile()
		code = emit(fn)
		assert code == "function return_undefined_1() {\nreturn undefined;\n}"
