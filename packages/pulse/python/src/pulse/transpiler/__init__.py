"""Python -> JavaScript transpiler system.

This module provides the full transpilation API for converting Python functions
to JavaScript. For basic usage, use the exports from the main `pulse` module:

    from pulse import javascript, Import, CssImport, import_js

For advanced use cases (custom transpilers, AST manipulation, module registration),
import from this module:

    from pulse.transpiler import JSExpr, JsTranspiler, register_module, ...
"""

# Core types
# Builtins system
from pulse.transpiler.builtins import ALL_METHODS as ALL_METHODS
from pulse.transpiler.builtins import BUILTINS as BUILTINS
from pulse.transpiler.builtins import DICT_METHODS as DICT_METHODS
from pulse.transpiler.builtins import LIST_METHODS as LIST_METHODS
from pulse.transpiler.builtins import METHOD_CLASSES as METHOD_CLASSES
from pulse.transpiler.builtins import SET_METHODS as SET_METHODS
from pulse.transpiler.builtins import STR_METHODS as STR_METHODS
from pulse.transpiler.builtins import BuiltinMethods as BuiltinMethods
from pulse.transpiler.builtins import DictMethods as DictMethods
from pulse.transpiler.builtins import ListMethods as ListMethods
from pulse.transpiler.builtins import SetMethods as SetMethods
from pulse.transpiler.builtins import StringMethods as StringMethods
from pulse.transpiler.builtins import emit_method as emit_method

# Constants system
from pulse.transpiler.constants import CONSTANTS_CACHE as CONSTANTS_CACHE
from pulse.transpiler.constants import JsConstant as JsConstant
from pulse.transpiler.constants import JsPrimitive as JsPrimitive
from pulse.transpiler.constants import JsValue as JsValue
from pulse.transpiler.constants import JsVar as JsVar
from pulse.transpiler.constants import const_to_js as const_to_js
from pulse.transpiler.constants import jsify as jsify

# Context
from pulse.transpiler.context import interpreted_mode as interpreted_mode
from pulse.transpiler.context import is_interpreted_mode as is_interpreted_mode
from pulse.transpiler.errors import JSCompilationError as JSCompilationError

# Function system
from pulse.transpiler.function import FUNCTION_CACHE as FUNCTION_CACHE
from pulse.transpiler.function import JSX_FUNCTION_CACHE as JSX_FUNCTION_CACHE
from pulse.transpiler.function import JsFunction as JsFunction
from pulse.transpiler.function import JsxFunction as JsxFunction
from pulse.transpiler.function import javascript as javascript

# Utilities
from pulse.transpiler.ids import generate_id as generate_id
from pulse.transpiler.ids import reset_id_counter as reset_id_counter
from pulse.transpiler.imports import CssImport as CssImport
from pulse.transpiler.imports import Import as Import

# Import system
from pulse.transpiler.imports import clear_import_registry as clear_import_registry
from pulse.transpiler.imports import import_js as import_js
from pulse.transpiler.imports import registered_imports as registered_imports

# Module registration - JS modules
from pulse.transpiler.js_module import JS_MODULES as JS_MODULES
from pulse.transpiler.js_module import JsModule as JsModule
from pulse.transpiler.js_module import register_js_module as register_js_module
from pulse.transpiler.jsx import JSXCallExpr as JSXCallExpr

# JS AST Utilities
from pulse.transpiler.nodes import ALLOWED_BINOPS as ALLOWED_BINOPS
from pulse.transpiler.nodes import ALLOWED_CMPOPS as ALLOWED_CMPOPS
from pulse.transpiler.nodes import ALLOWED_UNOPS as ALLOWED_UNOPS
from pulse.transpiler.nodes import JSEXPR_REGISTRY as JSEXPR_REGISTRY

# JS AST Nodes - Expressions
from pulse.transpiler.nodes import JSArray as JSArray
from pulse.transpiler.nodes import JSArrowFunction as JSArrowFunction

# JS AST Nodes - Statements
from pulse.transpiler.nodes import JSAssign as JSAssign
from pulse.transpiler.nodes import JSAugAssign as JSAugAssign
from pulse.transpiler.nodes import JSBinary as JSBinary
from pulse.transpiler.nodes import JSBlock as JSBlock
from pulse.transpiler.nodes import JSBoolean as JSBoolean
from pulse.transpiler.nodes import JSBreak as JSBreak
from pulse.transpiler.nodes import JSCall as JSCall
from pulse.transpiler.nodes import JSComma as JSComma
from pulse.transpiler.nodes import JSComputedProp as JSComputedProp
from pulse.transpiler.nodes import JSConstAssign as JSConstAssign
from pulse.transpiler.nodes import JSContinue as JSContinue
from pulse.transpiler.nodes import JSExpr as JSExpr
from pulse.transpiler.nodes import JSForOf as JSForOf
from pulse.transpiler.nodes import JSFunctionDef as JSFunctionDef
from pulse.transpiler.nodes import JSIdentifier as JSIdentifier
from pulse.transpiler.nodes import JSIf as JSIf

# JS AST Nodes - JSX
from pulse.transpiler.nodes import JSImport as JSImport
from pulse.transpiler.nodes import JSLogicalChain as JSLogicalChain
from pulse.transpiler.nodes import JSMember as JSMember
from pulse.transpiler.nodes import JSMemberCall as JSMemberCall
from pulse.transpiler.nodes import JSMultiStmt as JSMultiStmt
from pulse.transpiler.nodes import JSNew as JSNew
from pulse.transpiler.nodes import JSNode as JSNode
from pulse.transpiler.nodes import JSNull as JSNull
from pulse.transpiler.nodes import JSNumber as JSNumber
from pulse.transpiler.nodes import JSObjectExpr as JSObjectExpr
from pulse.transpiler.nodes import JSProp as JSProp
from pulse.transpiler.nodes import JSRaw as JSRaw
from pulse.transpiler.nodes import JSReturn as JSReturn
from pulse.transpiler.nodes import JSSingleStmt as JSSingleStmt
from pulse.transpiler.nodes import JSSpread as JSSpread
from pulse.transpiler.nodes import JSStmt as JSStmt
from pulse.transpiler.nodes import JSString as JSString
from pulse.transpiler.nodes import JSSubscript as JSSubscript
from pulse.transpiler.nodes import JSTemplate as JSTemplate
from pulse.transpiler.nodes import JSTertiary as JSTertiary
from pulse.transpiler.nodes import JSTransformer as JSTransformer
from pulse.transpiler.nodes import JSUnary as JSUnary
from pulse.transpiler.nodes import JSUndefined as JSUndefined
from pulse.transpiler.nodes import JSWhile as JSWhile
from pulse.transpiler.nodes import JSXElement as JSXElement
from pulse.transpiler.nodes import JSXFragment as JSXFragment
from pulse.transpiler.nodes import JSXProp as JSXProp
from pulse.transpiler.nodes import JSXSpreadProp as JSXSpreadProp
from pulse.transpiler.nodes import is_primary as is_primary

# Module registration - Python modules
from pulse.transpiler.py_module import PY_MODULES as PY_MODULES
from pulse.transpiler.py_module import PyModule as PyModule
from pulse.transpiler.py_module import PyModuleExpr as PyModuleExpr
from pulse.transpiler.py_module import register_module as register_module

# Transpiler
from pulse.transpiler.transpiler import JsTranspiler as JsTranspiler
