"""
JavaScript ReactDOM module.

Usage:
    from pulse.js.react_dom import createPortal
    createPortal(children, container)  # -> createPortal(children, container)

    # Also available as namespace:
    import pulse.js.react_dom as ReactDOM
    ReactDOM.createPortal(children, container)
"""

from typing import Any as _Any

# Import types from react module for consistency
from pulse.js.react import ReactNode as ReactNode
from pulse.transpiler.js_module import JsModule


def createPortal(
	children: ReactNode, container: _Any, key: str | None = None
) -> ReactNode:
	"""Creates a portal to render children into a different DOM subtree."""
	...


# ReactDOM is a namespace module where each export is a named import
JsModule.register(
	name="ReactDOM", src="react-dom", kind="namespace", values="named_import"
)
