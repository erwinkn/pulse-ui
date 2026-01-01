from typing import Any

import pulse as ps


@ps.react_component(ps.Import("AgGridReact", "ag-grid-react"))
def AgGridReact(key: str | None = None, **props: Any):
	"""Untyped wrapper around the AgGridReact component from ag-grid-react.
	Currently only accepts JSON-compatible props and no children.
	Support for passing functions and components as props is coming soon."""
	...
