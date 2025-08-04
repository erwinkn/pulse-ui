import json
import logging
from dataclasses import dataclass
from pathlib import Path

from mako.template import Template

from pulse.hooks import ReactiveState

from .routing import Layout, Route, RouteTree
from .reactive import IS_PRERENDERING

logger = logging.getLogger(__file__)


@dataclass
class CodegenConfig:
    """
    Configuration for code generation.

    Attributes:
        web_dir (str): Root directory for the web output.
        pulse_app_name (str): Name of the Pulse app directory.
        pulse_lib_path (str): Path to the Pulse library.
        pulse_app_dir (Path): Full path to the generated app directory.
    """

    web_dir: str = "pulse-web"
    """Root directory for the web output."""

    pulse_dir: str = "pulse"
    """Name of the Pulse app directory."""

    lib_path: str = "~/pulse-lib"
    """Path to the Pulse library."""

    @property
    def pulse_path(self) -> Path:
        """Full path to the generated app directory."""
        return Path(self.web_dir) / "app" / self.pulse_dir


# Mako template for the main layout
LAYOUT_TEMPLATE = Template(
    """import { PulseProvider, type PulseConfig } from "${lib_path}/pulse";
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
    """import {
  type RouteConfig,
  route,
  layout,
  index,
} from "@react-router/dev/routes";

export const routes = [
  layout("${pulse_dir}/_layout.tsx", [
${routes_str}
  ]),
] satisfies RouteConfig;
"""
)

# Mako template for route pages
ROUTE_PAGE_TEMPLATE = Template(
    """import { PulseView } from "${lib_path}/pulse";
import type { VDOM, ComponentRegistry } from "${lib_path}/vdom";

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
const initialVDOM: VDOM = ${vdom};

const path = "${route.unique_path()}";

export default function RouteComponent() {
  return (
    <PulseView
      initialVDOM={initialVDOM}
      externalComponents={externalComponents}
      path={path}
    />
  );
}
"""
)


def write_file_if_changed(path: Path, content: str) -> Path:
    """Write content to file only if it has changed."""
    if path.exists():
        try:
            current_content = path.read_text()
            if current_content == content:
                return path  # Skip writing, content is the same
        except Exception:
            # If we can't read the file for any reason, just write it
            pass

    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(content)
    return path


class Codegen:
    def __init__(
        self, routes: RouteTree, config: CodegenConfig, host="127.0.0.1", port=8000
    ) -> None:
        self.cfg = config
        self.routes = routes
        self.host = host
        self.port = port

    @property
    def output_folder(self):
        return self.cfg.pulse_path


    def generate_all(
        self,
    ):
        # Keep track of all generated files
        generated_files = [
            self.generate_layout_tsx(),
            self.generate_routes_ts(),
            *(self.generate_route(route) for route in self.routes.flat_tree.values()),
        ]
        generated_files = set(generated_files)

        # Clean up any remaining files that are not part of the generated files
        for path in self.output_folder.rglob("*"):
            if path.is_file() and path not in generated_files:
                try:
                    path.unlink()
                    logger.debug(f"Removed stale file: {path}")
                except Exception as e:
                    logger.warning(f"Could not remove stale file {path}: {e}")

    def generate_layout_tsx(self):
        """Generates the content of _layout.tsx"""
        content = str(
            LAYOUT_TEMPLATE.render_unicode(
                host=self.host, port=self.port, lib_path=self.cfg.lib_path
            )
        )
        # The underscore avoids an eventual naming conflict with a generated
        # /layout route.
        return write_file_if_changed(self.output_folder / "_layout.tsx", content)

    def generate_routes_ts(self):
        """Generate TypeScript code for the routes configuration."""
        routes_str = self._render_routes_ts(self.routes.tree, 2)
        content = str(
            ROUTES_CONFIG_TEMPLATE.render_unicode(
                routes_str=routes_str,
                pulse_dir=self.cfg.pulse_dir,
            )
        )
        return write_file_if_changed(self.output_folder / "routes.ts", content)

    def _render_routes_ts(self, routes: list[Route | Layout], indent_level: int) -> str:
        lines = []
        indent_str = "  " * indent_level
        for route in routes:
            if isinstance(route, Layout):
                children_str = ""
                if route.children:
                    children_str = f"\n{self._render_routes_ts(route.children, indent_level + 1)}\n{indent_str}"
                lines.append(
                    f'{indent_str}layout("{self.cfg.pulse_dir}/layouts/{route.file_path()}", [{children_str}]),'
                )
            else:
                if route.children:
                    children_str = f"\n{self._render_routes_ts(route.children, indent_level + 1)}\n{indent_str}"
                    lines.append(
                        f'{indent_str}route("{route.path}", "{self.cfg.pulse_dir}/routes/{route.file_path()}", [{children_str}]),'
                    )
                elif route.is_index:
                    lines.append(
                        f'{indent_str}index("{self.cfg.pulse_dir}/routes/{route.file_path()}"),'
                    )
                else:
                    lines.append(
                        f'{indent_str}route("{route.path}", "{self.cfg.pulse_dir}/routes/{route.file_path()}"),'
                    )
        return "\n".join(lines)

    def generate_route(self, route: Route | Layout):
        if isinstance(route, Layout):
            output_path = self.output_folder / "layouts" / route.file_path()
        else:
            output_path = self.output_folder / "routes" / route.file_path()
        # Generate initial UI tree by calling the route function
        with ReactiveState.create().start_render():
            token = IS_PRERENDERING.set(True)
            initial_node = route.render.fn()  # type: ignore
            IS_PRERENDERING.reset(token)
        vdom, _ = initial_node.render()
        content = str(
            ROUTE_PAGE_TEMPLATE.render_unicode(
                route=route,
                components=route.components or [],
                vdom=json.dumps(vdom, indent=2),
                lib_path=self.cfg.lib_path,
            )
        )
        return write_file_if_changed(output_path, content)
