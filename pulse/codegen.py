"""
TypeScript code generation for React components and routes.

This module handles generating TypeScript files for:
- Combined route entrypoints with inline component registries
- Routes configuration updates
"""

import json
import os
from pathlib import Path
from typing import Dict, List

from .html import ReactComponent, Route, UITreeNode


def generate_route_with_registry(route: Route, initial_ui_tree: Dict) -> str:
    """
    Generate TypeScript code for a route entrypoint with inline component registry.
    
    Args:
        route: Route object containing the route definition
        initial_ui_tree: The initial UI tree data structure
    
    Returns:
        TypeScript code as a string
    """
    # Generate component imports and registry
    if route.components:
        imports = []
        registry_entries = []
        
        for component in route.components:
            if component.is_default_export:
                import_line = f'import {component.export_name} from "{component.import_path}";'
            else:
                import_line = f'import {{ {component.export_name} }} from "{component.import_path}";'
            
            imports.append(import_line)
            registry_entries.append(f'  "{component.component_key}": {component.export_name},')
        
        imports_section = "\n".join(imports)
        registry_section = "\n".join(registry_entries)
        
        component_registry_code = f'''
// Component imports
{imports_section}

// Component registry
const componentRegistry: Record<string, ComponentType<any>> = {{
{registry_section}
}};'''
    else:
        component_registry_code = '''
// No components needed for this route
const componentRegistry: Record<string, ComponentType<any>> = {};'''
    
    # Serialize the UI tree to JSON string
    ui_tree_json = json.dumps(initial_ui_tree, indent=2)
    
    return f'''import {{ ReactiveUIContainer }} from "../ui-tree";
import {{ ComponentRegistryProvider }} from "../ui-tree/component-registry";
import type {{ ComponentType }} from "react";
{component_registry_code}

const initialTree = {ui_tree_json};

export default function RouteComponent() {{
  return (
    <ComponentRegistryProvider registry={{componentRegistry}}>
      <ReactiveUIContainer
        initialTree={{initialTree}}
        transport={{null}} // Will be set up later for WebSocket connection
      />
    </ComponentRegistryProvider>
  );
}}
'''


def generate_routes_config(routes: List[Route]) -> str:
    """
    Generate TypeScript code for the routes configuration.
    
    Args:
        routes: List of Route objects
    
    Returns:
        TypeScript code as a string
    """
    imports = ['import { type RouteConfig, index, route } from "@react-router/dev/routes";']
    route_entries = []
    
    for i, route_obj in enumerate(routes):
        # Convert path to safe filename
        safe_path = route_obj.path.replace("/", "_").replace("-", "_")
        if safe_path.startswith("_"):
            safe_path = safe_path[1:]
        if not safe_path:
            safe_path = "index"
        
        if route_obj.path == "/":
            route_entries.append(f'  index("routes/{safe_path}.tsx"),')
        else:
            route_entries.append(f'  route("{route_obj.path}", "routes/{safe_path}.tsx"),')
    
    routes_section = "\n".join(route_entries)
    
    return f'''{imports[0]}

export default [
{routes_section}
] satisfies RouteConfig;
'''


def write_generated_files(routes: List[Route], output_dir: str = "pulse-web/app"):
    """
    Generate and write all TypeScript files for the given routes.
    
    Args:
        routes: List of Route objects to process
        output_dir: Base directory to write files to
    """
    output_path = Path(output_dir)
    routes_dir = output_path / "routes"
    
    # Ensure directories exist
    routes_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate files for each route
    for route_obj in routes:
        # Convert path to safe filename
        safe_path = route_obj.path.replace("/", "_").replace("-", "_")
        if safe_path.startswith("_"):
            safe_path = safe_path[1:]
        if not safe_path:
            safe_path = "index"
        
        # Generate initial UI tree by calling the route function
        initial_node = route_obj.render_func()
        initial_ui_tree = initial_node.to_dict()
        
        # Generate route entrypoint with inline component registry
        route_code = generate_route_with_registry(route_obj, initial_ui_tree)
        
        route_file = routes_dir / f"{safe_path}.tsx"
        route_file.write_text(route_code)
    
    # Generate routes configuration
    routes_config_code = generate_routes_config(routes)
    routes_config_file = output_path / "routes.ts"
    routes_config_file.write_text(routes_config_code)
    
    print(f"Generated {len(routes)} route files in {routes_dir}")
    print(f"Updated routes configuration at {routes_config_file}")


if __name__ == "__main__":
    # Example usage
    from .html import define_react_component, define_route, div, h1, p
    
    # Define some React components
    Counter = define_react_component("counter", "../ui-tree/demo-components", "Counter", False)
    UserCard = define_react_component("user-card", "../ui-tree/demo-components", "UserCard", False)
    
    # Define a route
    @define_route("/example", components=["counter", "user-card"])
    def example_route():
        return div()[
            h1()["Example Route"],
            p()["This is a server-generated route with React components:"],
            Counter(count=5, label="Example Counter")[
                "This counter starts at 5"
            ],
            UserCard(name="John Doe", email="john@example.com")
        ]
    
    # Generate files
    write_generated_files([example_route])