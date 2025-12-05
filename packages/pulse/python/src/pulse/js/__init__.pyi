"""Type stubs for pulse.js module exports.

This file provides type hints for direct imports from pulse.js:
    from pulse.js import Set, Number, Array, Math, Date, Promise, etc.
"""

from __future__ import annotations

import pulse.js.console as _console
import pulse.js.json as _JSON
import pulse.js.math as _Math

# Import actual types from modules for re-export
from pulse.js.array import Array as Array
from pulse.js.date import Date as Date
from pulse.js.error import Error as Error
from pulse.js.map import Map as Map
from pulse.js.number import Number as Number
from pulse.js.object import Object as Object
from pulse.js.promise import Promise as Promise
from pulse.js.regexp import RegExp as RegExp
from pulse.js.set import Set as Set
from pulse.js.string import String as String
from pulse.js.weakmap import WeakMap as WeakMap
from pulse.js.weakset import WeakSet as WeakSet

JSON = _JSON
Math = _Math
console = _console
