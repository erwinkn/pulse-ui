import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from pulse.javascript.nodes import JSExpr

if TYPE_CHECKING:
    from .transpiler import JsTranspiler


@dataclass
class ReferenceTable:
    rename: dict[str, JSExpr]
    replace_function: dict[str, Callable[[ast.Call, "JsTranspiler"], JSExpr]]
    replace_method: dict[str, Callable[[ast.Call, "JsTranspiler"], JSExpr]]
