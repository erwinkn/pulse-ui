# Implementation Plan: Merge `javascript_v2` into Codegen System

## Overview

Rewrite `packages/pulse/python/src/pulse/codegen/templates/route.py` to use the `javascript_v2` registration system with unique IDs, eliminating name conflict resolution logic.

## Key Insight

The `javascript_v2` module already has excellent infrastructure:

- **`Import`** (`javascript_v2/imports.py`): Auto-registered with unique IDs, deduplication via global `_REGISTRY`
- **`JsFunction`** (`javascript_v2/function.py`): Auto-registered with unique IDs, deduplication via `FUNCTION_CACHE`
- **`JsConstant`** (`javascript_v2/constants.py`): Auto-registered with unique IDs, deduplication via `CONSTANTS_CACHE`
- **`generate_id()`** (`javascript_v2/ids.py`): Simple hex counter for unique IDs

The current `route.py` uses `NameRegistry` to resolve conflicts by renaming (e.g., `foo2`, `foo3`). The new system uses unique suffixes like `foo_1`, `foo_2`, `foo_a` which are guaranteed unique.

---

## Phase 1: Create the New `generate_route` Function

**File**: `packages/pulse/python/src/pulse/codegen/templates/route.py`

**New API signature:**

```python
def generate_route(
    path: str,
    imports: Sequence[Import],
    css_modules: Sequence[CssModule],
    css_imports: Sequence[CssImport],
    functions: Sequence[JsFunction],
    components: Sequence[ReactComponent],
) -> str:
```

**What gets deleted:**

- `RouteTemplate` class (the entire class)
- `NameRegistry` usage
- `ComponentInfo`, `CssModuleImport`, `CssModuleCtx` TypedDicts (replaced by simpler structures)
- `dynamic_selector()` function
- `RESERVED_NAMES` list (not needed with unique IDs)
- The old `render_route()` function

---

## Phase 2: Implement Import Generation

### Step 2.1: Group imports by source

Group all `Import` objects by their `src` property:

```python
def _group_imports_by_source(imports: Sequence[Import]) -> dict[str, list[Import]]:
    """Group imports by their source module."""
```

### Step 2.2: Resolve import ordering

Use `Import.before` constraints for topological sorting. Adapt the existing Kahn's algorithm from `codegen/imports.py:169-204` but simplified:

```python
def _order_import_sources(
    grouped: dict[str, list[Import]]
) -> list[str]:
    """Return source paths in topologically sorted order."""
```

### Step 2.3: Generate import statements

For each source, emit:

- Side-effect imports: `import "source";`
- Default imports: `import Name_id from "source";`
- Named imports: `import { name as name_id } from "source";`
- Type imports: `import type { name as name_id } from "source";`

---

## Phase 3: Implement Transpiled Code Output

### Step 3.1: Collect full dependency graph

Given a list of `JsFunction` objects, walk their dependencies recursively to get all `JsFunction` and `JsConstant` nodes:

```python
def _collect_function_graph(
    functions: Sequence[JsFunction]
) -> tuple[list[JsConstant], list[JsFunction]]:
    """Collect all constants and functions in dependency order."""
```

### Step 3.2: Output constants

```javascript
const X_0x3 = [1, 2, 3];
const Y_0x4 = new Date();
```

### Step 3.3: Output function stubs (placeholder for now)

```javascript
function A_0x5() {
  // TODO: transpiled body
}
```

The actual transpilation is deferred for later.

---

## Phase 4: Output Registries

### Step 4.1: CSS Modules Registry

Integrate with `pulse/css.py`:

- `CssModule`: has `id` and `source_path`
- Generate import with unique ID and add to registry

```javascript
import css_abc123def456 from "./path/to/module.css";

const cssModules = {
  css_abc123def456: css_abc123def456,
};
```

### Step 4.2: Function Registry

Map original function names to their unique JS names:

```javascript
const functions = {
  my_func: my_func_0x5,
  helper: helper_0x6,
};
```

### Step 4.3: React Component Registry

```javascript
const externalComponents: ComponentRegistry = {
    "Button": Button_0x1,
    "Link": Link_0x2,
    // Lazy components use RenderLazy
    "HeavyComponent": RenderLazy(() => import("./heavy").then((m) => ({ default: m.HeavyComponent }))),
};
```

---

## Phase 5: Integrate CSS System

**Modifications to `pulse/css.py`:**

Currently `CssModule` and `CssImport` have their own ID generation (`_module_id`, `_import_id`). We will:

**Keep the existing hash-based IDs** because:

- CSS modules need stable IDs across runs for caching
- The hash is content-based, which is good for CSS

**Integration**: Create `Import` objects for CSS modules:

```python
def css_module_to_import(module: CssModule) -> Import:
    """Convert a CssModule to an Import for the codegen system."""
    return Import.default(module.id, str(module.source_path))
```

---

## Phase 6: Migrate ReactComponent to Use Import Directly

The current `ReactComponent` extends `Imported` from `codegen/imports.py`. We will refactor it to use `Import` from `javascript_v2/imports.py` directly.

**Changes to `react_component.py`:**

1. Remove inheritance from `Imported`
2. Store an `Import` instance directly on the component
3. Delegate `expr` property to the `Import.expr`

```python
from pulse.transpiler.imports import Import

class ReactComponent(Generic[P]):
    """A React component that can be used within the UI tree."""

    import_: Import  # The import for this component
    props_spec: PropSpec
    fn_signature: Callable[P, Element]
    lazy: bool

    def __init__(
        self,
        name: str,
        src: str,
        *,
        is_default: bool = False,
        prop: str | None = None,
        lazy: bool = False,
        version: str | None = None,
        prop_spec: PropSpec | None = None,
        fn_signature: Callable[P, Element] = default_signature,
        extra_imports: tuple[Import, ...] | list[Import] | None = None,
    ):
        # Create the Import directly
        if is_default:
            self.import_ = Import.default(name, src, prop=prop)
        else:
            self.import_ = Import.named(name, src, prop=prop)

        # ... rest of init
        self.extra_imports: list[Import] = list(extra_imports or [])

    @property
    def name(self) -> str:
        return self.import_.name

    @property
    def src(self) -> str:
        return self.import_.src

    @property
    def is_default(self) -> bool:
        return self.import_.is_default

    @property
    def prop(self) -> str | None:
        return self.import_.prop

    @property
    def expr(self) -> str:
        return self.import_.expr
```

**Changes to `extra_imports`:**

- Change type from `list[ImportStatement]` to `list[Import]`
- Existing usages of `ImportStatement` for side-effect CSS imports become `Import.css(src)`

**Migration for existing component definitions:**

```python
# Before (simple side-effect):
extra_imports=[ImportStatement(src="@mantine/core/styles.css", side_effect=True)]

# After:
extra_imports=[Import.css("@mantine/core/styles.css")]

# Before (with ordering constraints):
extra_imports=[
    ImportStatement(
        src="@mantine/core/styles.css",
        side_effect=True,
        before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
    )
]

# After:
extra_imports=[
    Import.css(
        "@mantine/core/styles.css",
        before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
    )
]
```

**Files requiring migration:**

- `packages/pulse-mantine/python/src/pulse_mantine/core/provider.py` - MantineProvider with `before` constraints
- `packages/pulse-mantine/python/src/pulse_mantine/dates/dates_provider.py` - DatesProvider
- `packages/pulse-mantine/python/src/pulse_mantine/charts/chart_tooltip.py` - ChartTooltip

---

## Phase 7: Final Template Structure

The output should look like `example_route.tsx`:

```typescript
// Imports (grouped by source, ordered by constraints)
import { type ComponentRegistry, PulseView } from "pulse-ui-client";
import type { HeadersArgs } from "react-router";
import { Link as Link_0x1, Outlet as Outlet_0x2 } from "react-router";
import css_abc123 from "./styles.module.css";

// Constants
const X_0x3 = [1, 2, 3];

// Functions (in dependency order)
function A_0x5() {
    // transpiled body
}

function B_0x6() {
    // transpiled body
}

// Registries
const cssModules = {
    "css_abc123": css_abc123,
};

const functions = {
    "A": A_0x5,
    "B": B_0x6,
};

const externalComponents: ComponentRegistry = {
    "Link": Link_0x1,
    "Outlet": Outlet_0x2,
};

const path = "/my/route";

export default function RouteComponent() {
    return (
        <PulseView
            key={path}
            externalComponents={externalComponents}
            functions={functions}
            cssModules={cssModules}
            path={path}
        />
    );
}

// Headers function (unchanged)
function hasAnyHeaders(headers: Headers): boolean {
    return [...headers].length > 0;
}

export function headers({ actionHeaders, loaderHeaders }: HeadersArgs) {
    return hasAnyHeaders(actionHeaders) ? actionHeaders : loaderHeaders;
}
```

---

## Implementation Checklist

### Files to Modify

1. **`packages/pulse/python/src/pulse/codegen/templates/route.py`** - Complete rewrite
   - Delete: `RouteTemplate`, `ComponentInfo`, `CssModuleImport`, `CssModuleCtx`, `dynamic_selector`, `RESERVED_NAMES`, `render_route`
   - Add: `generate_route()` and helper functions

2. **`packages/pulse/python/src/pulse/css.py`** - Minor additions
   - Add: `css_module_to_import()` helper function

3. **`packages/pulse/python/src/pulse/react_component.py`** - Refactor to use Import
   - Remove: inheritance from `Imported`
   - Add: `import_: Import` attribute
   - Change: `extra_imports` type from `list[ImportStatement]` to `list[Import]`
   - Add: property delegations for `name`, `src`, `is_default`, `prop`, `expr`

### Files That May Need Updates (callers of `render_route`)

Search for usages of `render_route` and update them to use the new API.

### Files That May Need Updates (callers using `extra_imports` with `ImportStatement`)

Search for usages of `ReactComponent` or `react_component` with `extra_imports` and update to use `Import` objects.

### Files to Keep As-Is

- `packages/pulse/python/src/pulse/javascript_v2/imports.py` - Already good
- `packages/pulse/python/src/pulse/javascript_v2/function.py` - Already good
- `packages/pulse/python/src/pulse/javascript_v2/constants.py` - Already good
- `packages/pulse/python/src/pulse/javascript_v2/ids.py` - Already good

### Files That Can Be Deprecated/Deleted

- `packages/pulse/python/src/pulse/codegen/utils.py` (`NameRegistry`) - No longer needed if nothing else uses it
- `packages/pulse/python/src/pulse/codegen/imports.py` - The `Imported` class is no longer needed after ReactComponent migration. Check if `Imports` and `ImportStatement` are still used elsewhere before deleting.

---

## Proposed Function Structure

```python
# packages/pulse/python/src/pulse/codegen/templates/route.py

from pulse.transpiler.imports import Import, registered_imports
from pulse.transpiler.function import JsFunction
from pulse.transpiler.constants import JsConstant
from pulse.css import CssModule, CssImport
from pulse.react_component import ReactComponent

def generate_route(
    path: str,
    imports: Sequence[Import] | None = None,
    css_modules: Sequence[CssModule] | None = None,
    css_imports: Sequence[CssImport] | None = None,
    functions: Sequence[JsFunction] | None = None,
    components: Sequence[ReactComponent] | None = None,
) -> str:
    """Generate a route file with all imports, functions, and components."""

    # 1. Collect all imports (from explicit + css + components)
    all_imports = _collect_all_imports(imports, css_modules, css_imports, components)

    # 2. Collect function graph (constants + functions in order)
    constants, funcs = _collect_function_graph(functions or [])

    # 3. Generate output sections
    output_parts = []

    # Section: Imports
    output_parts.append(_generate_imports_section(all_imports))

    # Section: Constants
    if constants:
        output_parts.append(_generate_constants_section(constants))

    # Section: Functions
    if funcs:
        output_parts.append(_generate_functions_section(funcs))

    # Section: Registries
    output_parts.append(_generate_registries_section(
        css_modules or [],
        funcs,
        components or [],
    ))

    # Section: Route component
    output_parts.append(_generate_route_component(path))

    # Section: Headers function
    output_parts.append(_generate_headers_function())

    return "\n".join(output_parts)
```

---

## Dependencies Between Components

```
Import (javascript_v2)
   ^
   |
   +-- CssModule (css.py) --> css_module_to_import()
   |
   +-- CssImport (css.py) --> side-effect import
   |
   +-- ReactComponent (react_component.py) --> uses Import directly via self.import_
   |
   +-- JsFunction (javascript_v2)
          |
          +-- JsConstant (javascript_v2)
```

---

## Resolved Questions

1. **Function registry**: The `functions` registry will be used later, but no need to integrate it into `PulseView` yet. Generate the registry in the route file for future use.

2. **Lazy components**: Lazy components should continue using `RenderLazy`. The codegen will emit:

   ```javascript
   "HeavyComponent": RenderLazy(() => import("./heavy").then((m) => ({ default: m.HeavyComponent }))),
   ```

3. **Extra imports on components**: `ReactComponent.extra_imports` will use `Import` objects from the new system (see Phase 6). This is part of the ReactComponent migration.

---

## Follow-up Tasks (Out of Scope for This Plan)

The following items are intentionally deferred to keep this plan focused:

1. **PyBuiltin handling**: The `JsFunction` dependency analysis identifies Python builtins (e.g., `len`, `range`, `print`) wrapped in `PyBuiltin`. These need to be mapped to JavaScript equivalents during transpilation. This should be addressed when implementing the actual function transpilation.
