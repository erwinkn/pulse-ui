"""v2 transpiler with pure data node AST."""

# Ensure built-in Python modules (e.g., math) are registered on import.
from pulse.transpiler import modules as _modules  # noqa: F401

# Asset registry (unified for Import and DynamicImport)
from pulse.transpiler.assets import LocalAsset as LocalAsset
from pulse.transpiler.assets import clear_asset_registry as clear_asset_registry
from pulse.transpiler.assets import get_registered_assets as get_registered_assets
from pulse.transpiler.assets import register_local_asset as register_local_asset

# Builtins
from pulse.transpiler.builtins import BUILTINS as BUILTINS
from pulse.transpiler.builtins import emit_method as emit_method

# Dynamic import primitive
from pulse.transpiler.dynamic_import import DynamicImport as DynamicImport
from pulse.transpiler.dynamic_import import import_ as import_

# Emit context
from pulse.transpiler.emit_context import EmitContext as EmitContext

# Errors
from pulse.transpiler.errors import TranspileError as TranspileError

# Function system
from pulse.transpiler.function import FUNCTION_CACHE as FUNCTION_CACHE

# Constant hoisting
from pulse.transpiler.function import Constant as Constant
from pulse.transpiler.function import JsFunction as JsFunction
from pulse.transpiler.function import analyze_deps as analyze_deps
from pulse.transpiler.function import clear_function_cache as clear_function_cache
from pulse.transpiler.function import (
	collect_function_graph as collect_function_graph,
)
from pulse.transpiler.function import javascript as javascript
from pulse.transpiler.function import registered_constants as registered_constants
from pulse.transpiler.function import registered_functions as registered_functions

# ID generator
from pulse.transpiler.id import next_id as next_id
from pulse.transpiler.id import reset_id_counter as reset_id_counter

# Import utilities
from pulse.transpiler.imports import Import as Import
from pulse.transpiler.imports import ImportKind as ImportKind
from pulse.transpiler.imports import caller_file as caller_file
from pulse.transpiler.imports import clear_import_registry as clear_import_registry
from pulse.transpiler.imports import get_registered_imports as get_registered_imports
from pulse.transpiler.imports import is_absolute_path as is_absolute_path
from pulse.transpiler.imports import is_local_path as is_local_path
from pulse.transpiler.imports import is_relative_path as is_relative_path

# JS module system
from pulse.transpiler.js_module import JsModule as JsModule

# Global registry
from pulse.transpiler.nodes import EXPR_REGISTRY as EXPR_REGISTRY
from pulse.transpiler.nodes import UNDEFINED as UNDEFINED

# Expression nodes
from pulse.transpiler.nodes import Array as Array
from pulse.transpiler.nodes import Arrow as Arrow

# Statement nodes
from pulse.transpiler.nodes import Assign as Assign
from pulse.transpiler.nodes import Binary as Binary
from pulse.transpiler.nodes import Block as Block
from pulse.transpiler.nodes import Break as Break
from pulse.transpiler.nodes import Call as Call

# Type aliases
from pulse.transpiler.nodes import Continue as Continue

# Data nodes
from pulse.transpiler.nodes import Element as Element
from pulse.transpiler.nodes import Expr as Expr
from pulse.transpiler.nodes import ExprStmt as ExprStmt
from pulse.transpiler.nodes import ForOf as ForOf
from pulse.transpiler.nodes import Function as Function
from pulse.transpiler.nodes import Identifier as Identifier
from pulse.transpiler.nodes import If as If

# JSX wrapper
from pulse.transpiler.nodes import Jsx as Jsx
from pulse.transpiler.nodes import Literal as Literal
from pulse.transpiler.nodes import Member as Member
from pulse.transpiler.nodes import New as New
from pulse.transpiler.nodes import Node as Node
from pulse.transpiler.nodes import Object as Object
from pulse.transpiler.nodes import Prop as Prop
from pulse.transpiler.nodes import PulseNode as PulseNode
from pulse.transpiler.nodes import Return as Return
from pulse.transpiler.nodes import Spread as Spread
from pulse.transpiler.nodes import Stmt as Stmt
from pulse.transpiler.nodes import Subscript as Subscript
from pulse.transpiler.nodes import Template as Template
from pulse.transpiler.nodes import Ternary as Ternary
from pulse.transpiler.nodes import Throw as Throw
from pulse.transpiler.nodes import Unary as Unary
from pulse.transpiler.nodes import Undefined as Undefined
from pulse.transpiler.nodes import Value as Value
from pulse.transpiler.nodes import While as While

# Emit
from pulse.transpiler.nodes import emit as emit

# React components (JSX imports with typed call signature)
from pulse.transpiler.react_component import react_component as react_component

# Transpiler
from pulse.transpiler.transpiler import Transpiler as Transpiler
from pulse.transpiler.transpiler import transpile as transpile
