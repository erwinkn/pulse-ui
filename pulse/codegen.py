"""
TypeScript code generation for React components and routes.

This module handles generating TypeScript files for:
- Combined route entrypoints with inline component registries
- Routes configuration updates
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from mako.template import Template

from .html import ReactComponent, Route, UITreeNode, prepare_ui_response


# Mako template for route component with inline registry
ROUTE_TEMPLATE = Template("""import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import { WebSocketTransport } from "../ui-tree/transport";
import type { ComponentType } from "react";

% if components:
// Component imports
% for component in components:
% if component.is_default_export:
import ${component.export_name} from "${component.import_path}";
% else:
import { ${component.export_name} } from "${component.import_path}";
% endif
% endfor

// Component registry
const componentRegistry: Record<string, ComponentType<any>> = {
% for component in components:
  "${component.component_key}": ${component.export_name},
% endfor
};
% else:
// No components needed for this route
const componentRegistry: Record<string, ComponentType<any>> = {};
% endif

const initialTree = ${ui_tree_json};

const callbackInfo = ${callback_info_json};

// Create WebSocket transport for server communication
const transport = new WebSocketTransport("ws://${host}:${port}/ws");

export default function RouteComponent() {
  return (
    <ComponentRegistryProvider registry={componentRegistry}>
      <ReactiveUIContainer
        initialTree={initialTree}
        callbackInfo={callbackInfo}
        transport={transport}
      />
    </ComponentRegistryProvider>
  );
}
""")


# Mako template for routes configuration
ROUTES_CONFIG_TEMPLATE = Template("""import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
% if not routes:

% else:
% for route_obj in routes:
<%
    # Convert path to safe filename
    safe_path = route_obj.path.replace("/", "_").replace("-", "_")
    if safe_path.startswith("_"):
        safe_path = safe_path[1:]
    if not safe_path:
        safe_path = "index"
%>
% if route_obj.path == "/":
  index("routes/${safe_path}.tsx"),
% else:
  route("${route_obj.path}", "routes/${safe_path}.tsx"),
% endif
% endfor
% endif
] satisfies RouteConfig;
""")


def generate_route_with_registry(
    route: Route,
    initial_ui_tree: Dict,
    callback_info: Optional[Dict] = None,
    host: str = "localhost",
    port: int = 8000,
) -> str:
    """
    Generate TypeScript code for a route entrypoint with inline component registry.

    Args:
        route: Route object containing the route definition
        initial_ui_tree: The initial UI tree data structure
        callback_info: Callback information for client-side handling
        host: Backend server host for WebSocket connection
        port: Backend server port for WebSocket connection

    Returns:
        TypeScript code as a string
    """
    return str(
        ROUTE_TEMPLATE.render_unicode(
            components=route.components or [],
            ui_tree_json=json.dumps(initial_ui_tree, indent=2),
            callback_info_json=json.dumps(callback_info or {}, indent=2),
            host=host,
            port=port,
        )
    )


def generate_routes_config(routes: List[Route]) -> str:
    """
    Generate TypeScript code for the routes configuration.

    Args:
        routes: List of Route objects

    Returns:
        TypeScript code as a string
    """
    return str(ROUTES_CONFIG_TEMPLATE.render_unicode(routes=routes))


def generate_all_routes(
    host: str = "localhost",
    port: int = 8000,
    output_dir: str = "pulse-web/app/pulse",
    clear_existing_callbacks: bool = False,
):
    """
    Complete route generation workflow: get routes, clear callbacks if needed, and write files.

    Args:
        host: Backend server host for WebSocket connection
        port: Backend server port for WebSocket connection
        output_dir: Base directory to write files to
        clear_existing_callbacks: Whether to clear existing callbacks before generation

    Returns:
        int: Number of routes generated
    """
    import logging
    from .routes import get_all_routes
    from .html import clear_callbacks

    logger = logging.getLogger(__name__)

    if clear_existing_callbacks:
        clear_callbacks()

    routes = get_all_routes()
    write_generated_files(routes, output_dir, host, port)

    if routes:
        logger.info(
            f"Generated {len(routes)} routes with WebSocket endpoint ws://{host}:{port}/ws"
        )
    else:
        logger.warning("No routes found to generate")

    return len(routes)


def write_generated_files(
    routes: List[Route],
    output_dir: str = "pulse-web/app/pulse",
    host: str = "localhost",
    port: int = 8000,
):
    """
    Generate and write all TypeScript files for the given routes.

    Args:
        routes: List of Route objects to process
        output_dir: Base directory to write files to
        host: Backend server host for WebSocket connection
        port: Backend server port for WebSocket connection
    """
    output_path = Path(output_dir)
    routes_path = output_path / "routes"

    # Ensure directories exist
    output_path.mkdir(parents=True, exist_ok=True)
    routes_path.mkdir(parents=True, exist_ok=True)

    # Clean up old generated route files
    # Only remove .tsx files that look like generated routes, preserve any manual files
    existing_files = list(routes_path.glob("*.tsx"))
    if existing_files:
        print(f"🧹 Cleaning up {len(existing_files)} existing route files...")
        for file_path in existing_files:
            try:
                file_path.unlink()
                print(f"   Removed: {file_path.name}")
            except Exception as e:
                print(f"   Warning: Could not remove {file_path.name}: {e}")

    # Also clean up old component registry files (legacy)
    legacy_files = list(routes_path.glob("*_component-registry.ts"))
    if legacy_files:
        print(f"🧹 Cleaning up {len(legacy_files)} legacy component registry files...")
        for file_path in legacy_files:
            try:
                file_path.unlink()
                print(f"   Removed: {file_path.name}")
            except Exception as e:
                print(f"   Warning: Could not remove {file_path.name}: {e}")

    # Generate files for each route
    for route_obj in routes:
        # Convert path to safe filename
        safe_path = route_obj.path.replace("/", "_").replace("-", "_")
        if safe_path.startswith("_"):
            safe_path = safe_path[1:]
        if not safe_path:
            safe_path = "index"

        # Generate initial UI tree and callback info by calling the route function
        initial_node = route_obj.render_func()
        initial_ui_tree, callback_info = prepare_ui_response(initial_node)

        # Generate route entrypoint with inline component registry
        route_code = generate_route_with_registry(
            route_obj, initial_ui_tree, callback_info, host, port
        )

        route_file = routes_path / f"{safe_path}.tsx"
        route_file.write_text(route_code)

    # Generate routes configuration
    routes_config_code = generate_routes_config(routes)
    routes_config_file = output_path / "routes.ts"
    routes_config_file.write_text(routes_config_code)

    print(f"Generated {len(routes)} route files in {routes_path}")
    print(f"Updated routes configuration at {routes_config_file}")


if __name__ == "__main__":
    # Example usage
    from .html import define_react_component, define_route, div, h1, p

    # Define some React components
    Counter = define_react_component(
        "counter", "../ui-tree/demo-components", "Counter", False
    )
    UserCard = define_react_component(
        "user-card", "../ui-tree/demo-components", "UserCard", False
    )

    # Define a route
    @define_route("/example", components=["counter", "user-card"])
    def example_route():
        return div()[
            h1()["Example Route"],
            p()["This is a server-generated route with React components:"],
            Counter(count=5, label="Example Counter")["This counter starts at 5"],
            UserCard(name="John Doe", email="john@example.com"),
        ]

    # Generate files
    write_generated_files([example_route])
