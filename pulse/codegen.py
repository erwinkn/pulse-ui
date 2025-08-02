"""
TypeScript code generation for React components and routes.

This module handles generating TypeScript files for:
- A single server config file
- A routes configuration file for the client-side router
- A page for each route that renders the Pulse component
"""

import json
from pathlib import Path
import logging
from typing import List, TYPE_CHECKING, Dict

from mako.template import Template

from pulse.reactive import ReactiveContext

if TYPE_CHECKING:
    from .app import App
    from .routing import Route

from .vdom import VDOMNode


class RouteTreeNode:
    def __init__(self, route: "Route"):
        self.route = route
        self.children: list["RouteTreeNode"] = []

    def add_child(self, node: "RouteTreeNode"):
        self.children.append(node)


class CodegenConfig:
    def __init__(
        self,
        web_dir: str = "pulse-web",
        pulse_app_name: str = "pulse",
        pulse_lib_path: str = "~/pulse-lib",
    ):
        self.web_dir = web_dir
        self.pulse_app_name = pulse_app_name
        self.pulse_lib_path = pulse_lib_path
        self.pulse_app_dir = Path(web_dir) / "app" / pulse_app_name


# Mako template for the main layout
LAYOUT_TEMPLATE = Template(
    """import { PulseProvider, type PulseConfig } from "${pulse_lib_path}/pulse";
import { Outlet } from "react-router";

// This config is imported by the layout and used to initialize the client
export const config: PulseConfig = {
  serverAddress: "${host}",
  serverPort: ${port},
};

export default function PulseLayout() {
  return (
    <PulseProvider config={config}>
      <Outlet />
    </PulseProvider>
  );
}
"""
)

# Mako template for routes configuration
ROUTES_CONFIG_TEMPLATE = Template(
    """
<%def name="render_routes(routes)">
% for node in routes:
  % if node.children:
    route("${node.route.path.lstrip('/')}", "${pulse_app_name}/routes/${node.route.get_safe_path()}.tsx", [
      ${render_routes(node.children)}
    ]),
  % else:
    % if node.route.is_index:
      index("${pulse_app_name}/routes/${node.route.get_safe_path()}.tsx"),
    % else:
      route("${node.route.path.lstrip('/')}", "${pulse_app_name}/routes/${node.route.get_safe_path()}.tsx"),
    % endif
  % endif
% endfor
</%def>

import {
  type RouteConfig,
  route,
  layout,
  index,
} from "@react-router/dev/routes";

export const routes = [
  layout("${pulse_app_name}/layout.tsx", [
    ${render_routes(route_tree)}
  ]),
] satisfies RouteConfig;
"""
)

# Mako template for route pages
ROUTE_PAGE_TEMPLATE = Template(
    """import { PulseView } from "${pulse_lib_path}/pulse";
import type { VDOM, ComponentRegistry } from "${pulse_lib_path}/vdom";

% if components:
// Component imports
% for component in components:
% if component.is_default:
import ${component.tag} from "${component.import_path}";
% else:
% if component.alias:
import { ${component.tag} as ${component.alias} } from "${component.import_path}";
% else:
import { ${component.tag} } from "${component.import_path}";
% endif
% endif
% endfor

// Component registry
const externalComponents: ComponentRegistry = {
% for component in components:
  "${component.key}": ${component.alias or component.tag},
% endfor
};
% else:
// No components needed for this route
const externalComponents: ComponentRegistry = {};
% endif

// The initial VDOM is bootstrapped from the server
const initialVDOM: VDOM = ${initial_vdom_json};

export default function RouteComponent() {
  return (
    <PulseView
      initialVDOM={initialVDOM}
      externalComponents={externalComponents}
    />
  );
}
"""
)


def generate_layout_file(host: str, port: int, pulse_lib_path: str) -> str:
    """Generates the content of _layout.tsx"""
    return str(
        LAYOUT_TEMPLATE.render_unicode(
            host=host, port=port, pulse_lib_path=pulse_lib_path
        )
    )


def generate_route_page(
    route: "Route", initial_vdom: VDOMNode, pulse_lib_path: str
) -> str:
    """Generates TypeScript code for a route page."""
    return str(
        ROUTE_PAGE_TEMPLATE.render_unicode(
            route=route,
            components=route.components or [],
            initial_vdom_json=json.dumps(initial_vdom, indent=2),
            pulse_lib_path=pulse_lib_path,
        )
    )


def generate_routes_config(routes: List["Route"], pulse_app_name: str) -> str:
    """
    Generate TypeScript code for the routes configuration.

    Args:
        routes: List of Route objects
        pulse_app_name: The name of the pulse app directory.

    Returns:
        TypeScript code as a string
    """
    # Build a tree from the flat list of routes
    route_nodes: Dict[str, RouteTreeNode] = {
        route.get_full_path(): RouteTreeNode(route) for route in routes
    }
    route_tree: list[RouteTreeNode] = []

    for route in routes:
        node = route_nodes[route.get_full_path()]
        if route.parent:
            parent_node = route_nodes[route.parent.get_full_path()]
            parent_node.add_child(node)
        else:
            route_tree.append(node)

    return str(
        ROUTES_CONFIG_TEMPLATE.render_unicode(
            route_tree=route_tree, pulse_app_name=pulse_app_name
        )
    )


def write_file_if_changed(file_path: Path, content: str) -> bool:
    """
    Write content to file only if it has changed.

    Args:
        file_path: Path to the file
        content: Content to write

    Returns:
        True if file was written, False if skipped (content unchanged)
    """
    if file_path.exists():
        try:
            current_content = file_path.read_text()
            if current_content == content:
                return False  # Skip writing, content is the same
        except Exception:
            # If we can't read the file for any reason, just write it
            pass

    file_path.write_text(content)
    return True


def generate_all_routes(
    app: "App",
    host: str = "localhost",
    port: int = 8000,
):
    """
    Complete route generation workflow: get routes, clear callbacks if needed, and write files.

    Args:
        app: The Pulse application instance.
        host: Backend server host for WebSocket connection.
        port: Backend server port for WebSocket connection.
    """

    logger = logging.getLogger(__name__)

    codegen_config = app.codegen
    routes = list(app.routes.values())
    output_path = codegen_config.pulse_app_dir
    routes_path = output_path / "routes"
    # Keep track of all generated files
    generated_files = set()

    # Ensure directories exist
    output_path.mkdir(parents=True, exist_ok=True)
    routes_path.mkdir(parents=True, exist_ok=True)

    # Generate _layout.tsx
    layout_code = generate_layout_file(
        host=host, port=port, pulse_lib_path=codegen_config.pulse_lib_path
    )
    layout_file = output_path / "layout.tsx"
    generated_files.add(layout_file)
    written = write_file_if_changed(layout_file, layout_code)
    if written:
        logger.info(f"Generated layout file at {layout_file}")
    else:
        logger.debug(f"Skipped layout file (unchanged): {layout_file}")

    # Generate files for each route
    routes_written_count = 0
    for route in routes:
        safe_path = route.get_safe_path()

        # Generate initial UI tree by calling the route function
        with ReactiveContext():
            initial_node = route.render_fn()
        vdom, _ = initial_node.render()

        # Generate route entrypoint with inline component registry
        route_code = generate_route_page(
            route,
            initial_vdom=vdom,
            pulse_lib_path=codegen_config.pulse_lib_path,
        )

        route_file = routes_path / f"{safe_path}.tsx"
        generated_files.add(route_file)
        written = write_file_if_changed(route_file, route_code)
        if written:
            routes_written_count += 1
        else:
            logger.debug(f"Skipped route file (unchanged): {route_file}")

    # Generate routes configuration
    routes_config_code = generate_routes_config(routes, codegen_config.pulse_app_name)
    routes_config_file = output_path / "routes.ts"
    generated_files.add(routes_config_file)
    routes_config_written = write_file_if_changed(
        routes_config_file, routes_config_code
    )

    # Clean up old files
    for path in output_path.rglob("*"):
        if path.is_file() and path not in generated_files:
            try:
                path.unlink()
                logger.debug(f"Removed stale file: {path}")
            except Exception as e:
                logger.warning(f"Could not remove stale file {path}: {e}")

    logger.info(
        f"Generated {len(routes)} routes in {routes_path} ({routes_written_count} files written)"
    )
    if routes_config_written:
        logger.info(f"Updated routes configuration at {routes_config_file}")
    else:
        logger.debug(f"Skipped routes configuration (unchanged): {routes_config_file}")
