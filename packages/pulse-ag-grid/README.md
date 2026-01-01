# Pulse AG Grid

Python bindings for AG Grid React data grid component.

## Status

**Minimal stub implementation.** Currently only accepts JSON-compatible props. Support for function/component props coming soon.

## Architecture

Wraps `AgGridReact` from `ag-grid-react` as a Pulse ReactComponent.

```
Python AgGridReact() → VDOM Node → pulse-client → ag-grid-react
```

## Folder Structure

```
src/pulse_ag_grid/
└── __init__.py    # AgGridReact component wrapper
```

## Usage

```python
from pulse_ag_grid import AgGridReact

def data_grid():
    return AgGridReact(
        rowData=[
            {"make": "Toyota", "model": "Celica", "price": 35000},
            {"make": "Ford", "model": "Mondeo", "price": 32000},
        ],
        columnDefs=[
            {"field": "make"},
            {"field": "model"},
            {"field": "price"},
        ],
    )
```

## Limitations

- Only JSON-serializable props supported
- No function props (cellRenderer, valueGetter, etc.)
- No component props (custom cell components)

## Roadmap

- [ ] Support function props via transpilation
- [ ] Support component props via component registry
- [ ] Add typed prop definitions
