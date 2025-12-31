"""Type stubs for pulse.js2 module exports.

This file provides type hints for direct imports from pulse.js2:
    from pulse.js2 import Set, Number, Array, Math, Date, Promise, etc.
"""

from typing import Any as _Any
from typing import NoReturn as _NoReturn

import pulse.js2.console
import pulse.js2.document
import pulse.js2.json
import pulse.js2.math
import pulse.js2.navigator
import pulse.js2.window

# Re-export type definitions for use in user code
from pulse.js2._types import (
	Clipboard as Clipboard,
)
from pulse.js2._types import (
	ClipboardItem as ClipboardItem,
)
from pulse.js2._types import (
	CSSStyleDeclaration as CSSStyleDeclaration,
)
from pulse.js2._types import (
	Element as Element,
)
from pulse.js2._types import (
	Event as Event,
)
from pulse.js2._types import (
	HTMLCollection as HTMLCollection,
)
from pulse.js2._types import (
	HTMLElement as HTMLElement,
)
from pulse.js2._types import (
	JSIterable as JSIterable,
)
from pulse.js2._types import (
	JSIterator as JSIterator,
)
from pulse.js2._types import (
	JSIteratorResult as JSIteratorResult,
)
from pulse.js2._types import (
	JSONReplacer as JSONReplacer,
)
from pulse.js2._types import (
	JSONReviver as JSONReviver,
)
from pulse.js2._types import (
	JSONValue as JSONValue,
)
from pulse.js2._types import (
	NodeList as NodeList,
)
from pulse.js2._types import (
	Range as Range,
)
from pulse.js2._types import (
	Selection as Selection,
)

# Re-export classes with proper generic types
from pulse.js2.array import Array as Array
from pulse.js2.date import Date as Date
from pulse.js2.error import Error as Error
from pulse.js2.error import EvalError as EvalError
from pulse.js2.error import RangeError as RangeError
from pulse.js2.error import ReferenceError as ReferenceError
from pulse.js2.error import SyntaxError as SyntaxError
from pulse.js2.error import TypeError as TypeError
from pulse.js2.error import URIError as URIError
from pulse.js2.map import Map as Map
from pulse.js2.number import Number as Number
from pulse.js2.object import Object as Object
from pulse.js2.object import PropertyDescriptor as PropertyDescriptor
from pulse.js2.promise import Promise as Promise
from pulse.js2.promise import PromiseWithResolvers as PromiseWithResolvers
from pulse.js2.regexp import RegExp as RegExp
from pulse.js2.set import Set as Set
from pulse.js2.string import String as String
from pulse.js2.weakmap import WeakMap as WeakMap
from pulse.js2.weakset import WeakSet as WeakSet
from pulse.transpiler_v2.nodes import Undefined

# Re-export namespace modules
console = pulse.js2.console
document = pulse.js2.document
JSON = pulse.js2.json
Math = pulse.js2.math
navigator = pulse.js2.navigator
window = pulse.js2.window

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

# Primitive values
undefined: Undefined
