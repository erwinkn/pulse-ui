import logging
from dataclasses import dataclass
from pathlib import Path

from pulse.templates import LAYOUT_TEMPLATE, ROUTE_TEMPLATE, ROUTES_CONFIG_TEMPLATE

from .routing import Layout, Route, RouteTree

logger = logging.getLogger(__file__)


@dataclass
class CodegenConfig:
    """
    Configuration for code generation.

    Attributes:
        web_dir (str): Root directory for the web output.
        pulse_dir (str): Name of the Pulse app directory.
        lib_path (str): Path to the Pulse library.
        pulse_path (Path): Full path to the generated app directory.
    """

    web_dir: Path | str = "pulse-web"
    """Root directory for the web output."""

    pulse_dir: Path | str = "pulse"
    """Name of the Pulse app directory."""

    lib_path: Path | str = "pulse-react"
    """Path to the Pulse library."""

    @property
    def pulse_path(self) -> Path:
        """Full path to the generated app directory."""
        return Path(self.web_dir) / "app" / self.pulse_dir


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
    def __init__(self, routes: RouteTree, config: CodegenConfig) -> None:
        self.cfg = config
        self.routes = routes

    @property
    def output_folder(self):
        return self.cfg.pulse_path

    def generate_all(self, server_address: str):
        # Keep track of all generated files
        generated_files = [
            self.generate_layout_tsx(server_address),
            self.generate_routes_ts(),
            *(
                self.generate_route(route, server_address=server_address)
                for route in self.routes.flat_tree.values()
            ),
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

    def generate_layout_tsx(self, server_address: str):
        """Generates the content of _layout.tsx"""
        content = str(
            LAYOUT_TEMPLATE.render_unicode(
                server_address=server_address, lib_path=self.cfg.lib_path
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

    def generate_route(self, route: Route | Layout, server_address: str):
        if isinstance(route, Layout):
            output_path = self.output_folder / "layouts" / route.file_path()
        else:
            output_path = self.output_folder / "routes" / route.file_path()
        content = str(
            ROUTE_TEMPLATE.render_unicode(
                route=route,
                components=route.components or [],
                lib_path=self.cfg.lib_path,
                server_address=server_address,
            )
        )
        return write_file_if_changed(output_path, content)
