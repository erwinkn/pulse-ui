"""v2 transpiler with pure data node AST."""

# Builtins
from pulse.transpiler_v2.builtins import BUILTINS as BUILTINS
from pulse.transpiler_v2.builtins import emit_method as emit_method

# Errors
from pulse.transpiler_v2.errors import TranspileError as TranspileError

# Function system
from pulse.transpiler_v2.function import FUNCTION_CACHE as FUNCTION_CACHE
from pulse.transpiler_v2.function import JsFunction as JsFunction
from pulse.transpiler_v2.function import analyze_deps as analyze_deps
from pulse.transpiler_v2.function import clear_function_cache as clear_function_cache
from pulse.transpiler_v2.function import javascript as javascript
from pulse.transpiler_v2.function import registered_functions as registered_functions

# Import utilities
from pulse.transpiler_v2.imports import Import as Import
from pulse.transpiler_v2.imports import clear_import_registry as clear_import_registry
from pulse.transpiler_v2.imports import get_registered_imports as get_registered_imports

# JS module system
from pulse.transpiler_v2.js_module import JsModule as JsModule

# Global registry
from pulse.transpiler_v2.nodes import EXPR_REGISTRY as EXPR_REGISTRY
from pulse.transpiler_v2.nodes import UNDEFINED as UNDEFINED

# Expression nodes
from pulse.transpiler_v2.nodes import Array as Array
from pulse.transpiler_v2.nodes import Arrow as Arrow

# Statement nodes
from pulse.transpiler_v2.nodes import Assign as Assign
from pulse.transpiler_v2.nodes import Binary as Binary
from pulse.transpiler_v2.nodes import Block as Block
from pulse.transpiler_v2.nodes import Break as Break
from pulse.transpiler_v2.nodes import Call as Call

# Type aliases
from pulse.transpiler_v2.nodes import Child as Child
from pulse.transpiler_v2.nodes import Continue as Continue

# Data nodes
from pulse.transpiler_v2.nodes import Element as Element
from pulse.transpiler_v2.nodes import Expr as Expr
from pulse.transpiler_v2.nodes import ExprStmt as ExprStmt
from pulse.transpiler_v2.nodes import ForOf as ForOf
from pulse.transpiler_v2.nodes import Function as Function
from pulse.transpiler_v2.nodes import Identifier as Identifier
from pulse.transpiler_v2.nodes import If as If
from pulse.transpiler_v2.nodes import Literal as Literal
from pulse.transpiler_v2.nodes import Member as Member
from pulse.transpiler_v2.nodes import New as New
from pulse.transpiler_v2.nodes import Node as Node
from pulse.transpiler_v2.nodes import Object as Object
from pulse.transpiler_v2.nodes import Prop as Prop
from pulse.transpiler_v2.nodes import PulseNode as PulseNode
from pulse.transpiler_v2.nodes import Return as Return
from pulse.transpiler_v2.nodes import Spread as Spread
from pulse.transpiler_v2.nodes import StmtNode as StmtNode
from pulse.transpiler_v2.nodes import Subscript as Subscript
from pulse.transpiler_v2.nodes import Template as Template
from pulse.transpiler_v2.nodes import Ternary as Ternary
from pulse.transpiler_v2.nodes import Throw as Throw
from pulse.transpiler_v2.nodes import Unary as Unary
from pulse.transpiler_v2.nodes import Undefined as Undefined
from pulse.transpiler_v2.nodes import Value as Value
from pulse.transpiler_v2.nodes import While as While

# Emit
from pulse.transpiler_v2.nodes import emit as emit

# React components (JSX imports with typed call signature)
from pulse.transpiler_v2.react_component import ReactComponent as ReactComponent
from pulse.transpiler_v2.react_component import react_component as react_component
from pulse.transpiler_v2.react_component import (
	registered_react_components as registered_react_components,
)

# Transpiler
from pulse.transpiler_v2.transpiler import Transpiler as Transpiler
from pulse.transpiler_v2.transpiler import transpile as transpile
