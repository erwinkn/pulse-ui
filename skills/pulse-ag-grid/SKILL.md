---
name: pulse-ag-grid
description: Python bindings for the AG Grid React data grid. Use when building data tables with pulse-ag-grid, passing rowData/columnDefs from server state, paginating large datasets, theming the grid, or debugging grids that render stale data or silently lack features.
---

# Pulse AG Grid

Thin Python wrapper around [AG Grid](https://www.ag-grid.com/react-data-grid/). It exposes one component, `AgGridReact`, defined as an untyped `@ps.react_component` over `ps.Import("AgGridReact", "ag-grid-react")`. Every keyword argument passes straight through as a React prop on the grid. Only JSON-serializable props are supported, and it takes no children.

## Quick Reference

```python
import pulse as ps
from pulse_ag_grid import AgGridReact

ps.div(style={"height": "400px"})[      # container needs explicit height
    AgGridReact(
        rowData=rows,                    # list of plain dicts
        columnDefs=[{"field": "name"}],  # JSON-compatible values only
        defaultColDef={"sortable": True, "filter": True},
    )
]
```

## Setup

```bash
uv add pulse-ag-grid
```

The package imports `ag-grid-react` without an npm version pin and registers no npm requirement with Pulse's dependency sync, so make sure `ag-grid-react` and `ag-grid-community` are installed in the app's web directory (e.g. `bun add ag-grid-react ag-grid-community`).

AG Grid v33+ also requires one-time module registration on the JS side. A local side-effect import handles it:

```python
ps.Import("./ag_grid_setup.js", side_effect=True)
```

```js
// ag_grid_setup.js
import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";
ModuleRegistry.registerModules([AllCommunityModule]);
```

The grid needs a container with explicit height, or `domLayout="autoHeight"` to size to row count.

## Core Limitation: JSON-Serializable Props Only

The current implementation only supports JSON-compatible props:

- row data must be plain dicts; column definitions must use JSON-compatible values
- function props (`valueGetter`, `cellRenderer`, `valueFormatter` as functions) are not supported
- custom cell components are not supported, and the component takes no children
- per the package contract this covers event callbacks too (`onCellClicked`, `onSelectionChanged`, ...): the wrapper can render and configure the grid, but grid events cannot reach server state yet

Function and component prop support is planned but not implemented. Workarounds, in order of preference:

1. **Compute server-side.** Derive, format, and filter in Python before passing `rowData`: formatted strings, precomputed flags, joined display fields.
2. **AG Grid expression strings.** Wherever AG Grid accepts a string expression instead of a function, it is just a string and passes through fine, e.g. `{"field": "total", "valueGetter": "data.price * data.qty"}` or `"cellClassRules": {"negative": "x < 0"}`.
3. **Own wrapper with local JS.** For behavior that genuinely needs functions or components, write your own `@ps.react_component` around a local JS component that wraps `AgGridReact` and defines the functions on the JS side (see the pulse skill's JS interop reference).

## Reactive Updates: Pass Data as Top-Level Props

Wrapper props map one-to-one to AG Grid React props, and AG Grid React only reacts to changes in top-level props. Anything nested inside a `gridOptions` dict is read once at grid initialization and never re-read.

```python
# CORRECT: grid re-renders when state.rows changes
AgGridReact(rowData=state.rows, columnDefs=state.columns)

# WRONG: grid initializes with the first value and freezes there
AgGridReact(gridOptions={"rowData": state.rows, "columnDefs": state.columns})
```

Symptom of getting this wrong: the grid renders once, then stays frozen on stale data while server state moves on. Forcing a remount by changing `key` is not a reliable fix; move the values to top-level props instead. Reserve `gridOptions` for truly static configuration, and prefer top-level props even then.

## Pagination

`pagination=True` only pages rows already sent to the client; it is presentation, not data loading. Fine for moderate row counts. For large tables, paginate server-side and pass only the current page:

```python
class GridState(ps.State):
    page: int = 0
    page_size: int = 100
    rows: list[dict] = []

    def load_page(self):
        # SQL LIMIT/OFFSET (or equivalent) on the server
        self.rows = fetch_rows(limit=self.page_size, offset=self.page * self.page_size)

    def next_page(self):
        self.page += 1
        self.load_page()
```

Render your own pager controls next to the grid. AG Grid's infinite and server-side row models need a JS datasource callback (and the server-side row model is Enterprise-only), so this wrapper cannot use them.

## Enterprise-Only Features

`ag-grid-community` silently ignores Enterprise options instead of erroring. If a grid option does nothing, check its edition in the AG Grid docs first. Notable Enterprise-only features:

- cell range selection and range clipboard copy/paste (drag-select a block of cells, copy, paste) — Community has no built-in clipboard/range support
- row grouping, pivoting, aggregation
- set filters (`agSetColumnFilter`), Excel export, master/detail, server-side row model

The wrapper does not pin an AG Grid edition or version. Installing `ag-grid-enterprise`, registering its modules, and setting the license key are JS-side steps (use the same side-effect JS file as module registration).

## Theming

The wrapper imports no AG Grid CSS and configures no theme; what you need depends on the AG Grid version installed in the web app:

- **v33+ (Theming API):** the bundled default (Quartz) theme applies with no CSS imports. Custom theme objects (`themeQuartz.withParams(...)`) are JS values the wrapper cannot pass; the only `theme` value expressible from Python is the string `"legacy"`.
- **Legacy CSS themes** (v32 and earlier, or `theme="legacy"` on v33+): side-effect import the CSS from Python and put the theme class on the sized container:

```python
ps.Import("ag-grid-community/styles/ag-grid.css", side_effect=True)
ps.Import("ag-grid-community/styles/ag-theme-quartz.css", side_effect=True)

ps.div(className="ag-theme-quartz", style={"height": "400px"})[AgGridReact(...)]
```

With legacy themes, dark mode is a separate container class (`ag-theme-quartz-dark`), not a grid prop. If the app has a dark-mode toggle, switch the container's `className` from state; a grid whose headers stay light in dark mode usually has the wrong (or missing) theme class on the container.

## Complete Example

```python
import pulse as ps
from pulse_ag_grid import AgGridReact

class EmployeesState(ps.State):
    # e.g. loaded from a DataFrame: df.to_dict("records")
    rows: list[dict] = [
        {"id": 1, "name": "Alice Johnson", "department": "Engineering", "salary": 95000},
        {"id": 2, "name": "Bob Smith", "department": "Marketing", "salary": 75000},
        {"id": 3, "name": "Carol Williams", "department": "Engineering", "salary": 105000},
    ]

@ps.component
def EmployeeTable():
    with ps.init():
        state = EmployeesState()

    columns = [
        {"field": "id", "headerName": "ID", "width": 80, "pinned": "left"},
        {"field": "name", "headerName": "Name", "flex": 1},
        {"field": "department", "headerName": "Department", "filter": True},
        {"field": "salary", "headerName": "Salary", "type": "numericColumn"},
    ]

    return ps.div(style={"height": "400px", "width": "100%"})[
        AgGridReact(
            rowData=state.rows,          # top-level prop: updates propagate
            columnDefs=columns,
            defaultColDef={"sortable": True, "resizable": True},
            rowSelection="single",
            pagination=True,             # client-side paging of loaded rows
            paginationPageSize=20,
        )
    ]

app = ps.App([ps.Route("/", EmployeeTable)])
```

## Gotchas

- **Invisible grid:** no explicit container height and no `domLayout="autoHeight"` renders a 0px-tall grid.
- **Non-JSON values:** `NaN`, `datetime`, `Decimal`, and numpy scalars in row dicts do not serialize. With pandas, convert first (e.g. cast dates to strings, replace `NaN` with `None`) before `df.to_dict("records")`.
- **Frozen grid:** reactive values buried in `gridOptions`; move them to top-level props.
- **Feature does nothing:** it is probably Enterprise-only; Community ignores it silently.
- **Grid errors on load with v33+:** community modules not registered; add the side-effect setup JS from Setup above.
