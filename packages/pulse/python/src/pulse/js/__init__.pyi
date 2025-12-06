"""Type stubs for pulse.js module exports.

This file provides type hints for direct imports from pulse.js:
    from pulse.js import Set, Number, Array, Math, Date, Promise, etc.
"""

from typing import Any as _Any
from typing import NoReturn as _NoReturn

import pulse.js.console
import pulse.js.document
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
	NodeList as NodeList,
)
from pulse.js._types import (
	Range as Range,
)
from pulse.js._types import (
	Selection as Selection,
)

# Re-export classes with proper generic types
from pulse.js.array import Array as Array
from pulse.js.date import Date as Date
from pulse.js.error import Error as Error
from pulse.js.error import EvalError as EvalError
from pulse.js.error import RangeError as RangeError
from pulse.js.error import ReferenceError as ReferenceError
from pulse.js.error import SyntaxError as SyntaxError
from pulse.js.error import TypeError as TypeError
from pulse.js.error import URIError as URIError
from pulse.js.map import Map as Map
from pulse.js.number import Number as Number
from pulse.js.object import Object as Object
from pulse.js.object import PropertyDescriptor as PropertyDescriptor
from pulse.js.promise import Promise as Promise
from pulse.js.promise import PromiseWithResolvers as PromiseWithResolvers
from pulse.js.regexp import RegExp as RegExp
from pulse.js.set import Set as Set
from pulse.js.string import String as String
from pulse.js.weakmap import WeakMap as WeakMap
from pulse.js.weakset import WeakSet as WeakSet
from pulse.transpiler.nodes import JSUndefined

# Re-export namespace modules
console = pulse.js.console
document = pulse.js.document
JSON = pulse.js.json
Math = pulse.js.math
navigator = pulse.js.navigator
window = pulse.js.window

# Statement-like functions
def throw(x: _Any) -> _NoReturn:
	"""Throw a JavaScript error."""
	...

# Primitive values
undefined: JSUndefined
