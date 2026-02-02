"""Type stubs for pulse.js module exports.

This file provides type hints for direct imports from pulse.js:
    from pulse.js import Set, Number, Array, Math, Date, Promise, etc.
"""

from typing import Any as _Any
from typing import NoReturn as _NoReturn

import pulse.js.console
import pulse.js.crypto
import pulse.js.document
import pulse.js.intl
import pulse.js.json
import pulse.js.math
import pulse.js.navigator
import pulse.js.window

# Re-export type definitions for use in user code
from pulse.js._types import (
	Clipboard as Clipboard,
)
from pulse.js._types import (
	ClipboardItem as ClipboardItem,
)
from pulse.js._types import (
	CSSStyleDeclaration as CSSStyleDeclaration,
)
from pulse.js._types import (
	Element as Element,
)
from pulse.js._types import (
	Event as Event,
)
from pulse.js._types import (
	HTMLCollection as HTMLCollection,
)
from pulse.js._types import (
	HTMLElement as HTMLElement,
)
from pulse.js._types import (
	JSIterable as JSIterable,
)
from pulse.js._types import (
	JSIterator as JSIterator,
)
from pulse.js._types import (
	JSIteratorResult as JSIteratorResult,
)
from pulse.js._types import (
	JSONReplacer as JSONReplacer,
)
from pulse.js._types import (
	JSONReviver as JSONReviver,
)
from pulse.js._types import (
	JSONValue as JSONValue,
)
from pulse.js._types import (
	NodeList as NodeList,
)
from pulse.js._types import (
	Range as Range,
)
from pulse.js._types import (
	Selection as Selection,
)
from pulse.js.abort_controller import AbortController as AbortController
from pulse.js.abort_controller import AbortSignal as AbortSignal
from pulse.js.animation import Animation as Animation
from pulse.js.animation import ComputedEffectTiming as ComputedEffectTiming
from pulse.js.animation import ComputedKeyframe as ComputedKeyframe
from pulse.js.animation import DocumentTimeline as DocumentTimeline
from pulse.js.animation import DocumentTimelineOptions as DocumentTimelineOptions
from pulse.js.animation import EffectTiming as EffectTiming
from pulse.js.animation import Keyframe as Keyframe
from pulse.js.animation import KeyframeEffect as KeyframeEffect
from pulse.js.animation import KeyframeEffectOptions as KeyframeEffectOptions
from pulse.js.animation import OptionalEffectTiming as OptionalEffectTiming
from pulse.js.animation import PropertyIndexedKeyframes as PropertyIndexedKeyframes

# Re-export classes with proper generic types
from pulse.js.array import Array as Array
from pulse.js.array_buffer import ArrayBuffer as ArrayBuffer
from pulse.js.array_buffer import BigInt64Array as BigInt64Array
from pulse.js.array_buffer import BigUint64Array as BigUint64Array
from pulse.js.array_buffer import DataView as DataView
from pulse.js.array_buffer import Float32Array as Float32Array
from pulse.js.array_buffer import Float64Array as Float64Array
from pulse.js.array_buffer import Int8Array as Int8Array
from pulse.js.array_buffer import Int16Array as Int16Array
from pulse.js.array_buffer import Int32Array as Int32Array
from pulse.js.array_buffer import Uint8Array as Uint8Array
from pulse.js.array_buffer import Uint8ClampedArray as Uint8ClampedArray
from pulse.js.array_buffer import Uint16Array as Uint16Array
from pulse.js.array_buffer import Uint32Array as Uint32Array
from pulse.js.blob import Blob as Blob
from pulse.js.custom_event import CustomEvent as CustomEvent
from pulse.js.date import Date as Date
from pulse.js.dom_parser import DOMParser as DOMParser
from pulse.js.dom_parser import XMLSerializer as XMLSerializer
from pulse.js.error import Error as Error
from pulse.js.error import EvalError as EvalError
from pulse.js.error import RangeError as RangeError
from pulse.js.error import ReferenceError as ReferenceError
from pulse.js.error import SyntaxError as SyntaxError
from pulse.js.error import TypeError as TypeError
from pulse.js.error import URIError as URIError
from pulse.js.fetch_api import Headers as Headers
from pulse.js.fetch_api import Request as Request
from pulse.js.fetch_api import Response as Response
from pulse.js.file import File as File
from pulse.js.file_reader import FileReader as FileReader
from pulse.js.form_data import FormData as FormData
from pulse.js.intersection_observer import IntersectionObserver as IntersectionObserver
from pulse.js.map import Map as Map
from pulse.js.mutation_observer import MutationObserver as MutationObserver
from pulse.js.mutation_observer import (
	MutationObserverInit as MutationObserverInit,
)
from pulse.js.mutation_observer import (
	MutationRecord as MutationRecord,
)
from pulse.js.number import Number as Number
from pulse.js.object import Object as Object
from pulse.js.object import PropertyDescriptor as PropertyDescriptor
from pulse.js.performance_observer import PerformanceObserver as PerformanceObserver
from pulse.js.promise import Promise as Promise
from pulse.js.promise import PromiseWithResolvers as PromiseWithResolvers
from pulse.js.regexp import RegExp as RegExp
from pulse.js.resize_observer import ResizeObserver as ResizeObserver
from pulse.js.set import Set as Set
from pulse.js.string import String as String
from pulse.js.text_encoding import TextDecoder as TextDecoder
from pulse.js.text_encoding import TextEncoder as TextEncoder
from pulse.js.url import URL as URL
from pulse.js.url import URLSearchParams as URLSearchParams
from pulse.js.weakmap import WeakMap as WeakMap
from pulse.js.weakset import WeakSet as WeakSet
from pulse.transpiler.nodes import Undefined

# Re-export namespace modules
console = pulse.js.console
crypto = pulse.js.crypto
document = pulse.js.document
Intl = pulse.js.intl
JSON = pulse.js.json
Math = pulse.js.math
navigator = pulse.js.navigator
window = pulse.js.window

# Statement-like functions
def throw(x: _Any) -> _NoReturn:
	"""Throw a JavaScript error."""
	...

def obj(**kwargs: _Any) -> _Any:
	"""Create a plain JavaScript object literal.

	Use this instead of dict() when you need a plain JS object (e.g., for React style prop).

	Example:
		style=obj(display="block", color="red")
		# Transpiles to: style={{ display: "block", color: "red" }}
	"""
	...

# Global function bindings
def fetch(input: str | Request, init: _Any | None = None) -> _Any:
	"""Fetch a resource."""
	...

# Primitive values
undefined: Undefined
