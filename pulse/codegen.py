"""
TypeScript code generation for React components and routes.

This module handles generating TypeScript files for:
- A single server config file
- A routes configuration file for the client-side router
- A page for each route that renders the Pulse component
"""

import json
from pathlib import Path
from typing import List, TYPE_CHECKING
import logging

from mako.template import Template

from .vdom import VDOMNode

if TYPE_CHECKING:
    from .app import App, Route


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


# Mako template for config.ts
CONFIG_TEMPLATE = Template(
    """import type { PulseConfig } from "${pulse_lib_path}/pulse";

export const config: PulseConfig = {
  serverAddress: "${host}",
  serverPort: ${port},
};
"""
)

# Mako template for routes configuration
ROUTES_CONFIG_TEMPLATE = Template(
    """import { type RouteConfig, index, route } from "@react-router/dev/routes";

export const routes = [
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
  index("${pulse_app_name}/routes/${safe_path}.tsx"),
% else:
  route("${route_obj.path}", "${pulse_app_name}/routes/${safe_path}.tsx"),
% endif
% endfor
% endif
] satisfies RouteConfig;
"""
)

# Mako template for route pages
ROUTE_PAGE_TEMPLATE = Template(
    """import { Pulse, type PulseInit, type ComponentRegistry } from "${pulse_lib_path}/pulse";
import { SocketIOTransport } from "${pulse_lib_path}/transport";
import { config } from "../config";

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
const externalComponents: ComponentRegistry = {
% for component in components:
  "${component.component_key}": ${component.export_name},
% endfor
};
% else:
// No components needed for this route
const externalComponents: ComponentRegistry = {};
% endif

// Create WebSocket transport for server communication
const transport = new SocketIOTransport(`ws://<%text>${config.serverAddress}</%text>:<%text>${config.serverPort}</%text>`);

const pulseInit: PulseInit = {
    route: "${route.path}",
    initialVDOM: ${initial_vdom_json},
    externalComponents: externalComponents,
    transport: transport,
};

export default function RouteComponent() {
  return (
    <Pulse {...pulseInit} config={config} />
  );
}
"""
)


def generate_config_file(host: str, port: int, pulse_lib_path: str) -> str:
    """Generates the content of config.ts"""
    return str(
        CONFIG_TEMPLATE.render_unicode(
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
    return str(
        ROUTES_CONFIG_TEMPLATE.render_unicode(
            routes=routes, pulse_app_name=pulse_app_name
        )
    )


def clean_directory(path: Path):
    # Delete everything under output_path
    if path.exists() and path.is_dir():
        for item in path.iterdir():
            if item.is_dir():
                for subitem in item.rglob("*"):
                    try:
                        if subitem.is_file() or subitem.is_symlink():
                            subitem.unlink()
                        elif subitem.is_dir():
                            subitem.rmdir()
                    except Exception as e:
                        print(f"   Warning: Could not remove {subitem}: {e}")
                try:
                    item.rmdir()
                except Exception as e:
                    print(f"   Warning: Could not remove directory {item}: {e}")
            else:
                try:
                    item.unlink()
                except Exception as e:
                    print(f"   Warning: Could not remove file {item}: {e}")


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
    clean_directory(output_path)

    if not routes:
        logger.warning("No routes found to generate")
        return

    # Ensure directories exist
    output_path.mkdir(parents=True, exist_ok=True)
    routes_path.mkdir(parents=True, exist_ok=True)

    # Generate config.ts
    config_code = generate_config_file(
        host=host, port=port, pulse_lib_path=codegen_config.pulse_lib_path
    )
    config_file = output_path / "config.ts"
    config_file.write_text(config_code)
    logger.info(f"Generated server config at {config_file}")

    # Generate files for each route
    for route in routes:
        # Convert path to safe filename
        safe_path = route.path.replace("/", "_").replace("-", "_")
        if safe_path.startswith("_"):
            safe_path = safe_path[1:]
        if not safe_path:
            safe_path = "index"

        # Generate initial UI tree by calling the route function
        initial_node = route.render_fn()
        vdom, _ = initial_node.render()

        # Generate route entrypoint with inline component registry
        route_code = generate_route_page(
            route,
            initial_vdom=vdom,
            pulse_lib_path=codegen_config.pulse_lib_path,
        )

        route_file = routes_path / f"{safe_path}.tsx"
        route_file.write_text(route_code)

    # Generate routes configuration
    routes_config_code = generate_routes_config(routes, codegen_config.pulse_app_name)
    routes_config_file = output_path / "routes.ts"
    routes_config_file.write_text(routes_config_code)

    logger.info(f"Generated {len(routes)} routes in {routes_path}")
    logger.info(f"Updated routes configuration at {routes_config_file}")
