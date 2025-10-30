from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
	from pulse.app import App


@dataclass(slots=True)
class AppLoadResult:
	"""Description of a loaded Pulse app and related filesystem context."""

	target: str
	mode: Literal["path", "module"]
	app: App
	module_name: str
	app_var: str
	app_file: Path | None
	app_dir: Path | None
	server_cwd: Path | None


@dataclass(slots=True)
class CommandSpec:
	"""Instructions for launching a subprocess associated with the CLI."""

	name: str
	args: list[str]
	cwd: Path
	env: dict[str, str]
	on_spawn: Callable[[], None] | None = None
