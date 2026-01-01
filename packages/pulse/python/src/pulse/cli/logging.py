"""
Mode-aware CLI logging for Pulse.

In dev mode, uses Rich Console with colors.
In ci/prod mode or with --plain, uses plain print().
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Literal

from pulse.env import PulseEnv

if TYPE_CHECKING:
	from rich.console import Console

TagMode = Literal["colored", "plain"]


class CLILogger:
	"""Mode-aware CLI logger that adapts output based on pulse environment.

	Args:
		mode: The pulse environment mode (dev, ci, prod)
		plain: Force plain output without colors, even in dev mode
	"""

	mode: PulseEnv
	plain: bool
	_console: Console | None

	def __init__(self, mode: PulseEnv = "dev", *, plain: bool = False):
		self.mode = mode
		self.plain = plain
		self._console = None
		if mode == "dev" and not plain:
			from rich.console import Console

			self._console = Console()

	@property
	def is_plain(self) -> bool:
		"""Return True if using plain output (ci/prod mode or --plain flag)."""
		return self.mode != "dev" or self.plain

	def print(self, message: str) -> None:
		"""Print a message."""
		if self._console:
			self._console.print(message)
		else:
			print(message)

	def error(self, message: str) -> None:
		"""Print an error message."""
		if self._console:
			self._console.print(f"[red]Error:[/red] {message}")
		else:
			print(f"Error: {message}")

	def success(self, message: str) -> None:
		"""Print a success message."""
		if self._console:
			self._console.print(f"[green]✓[/green] {message}")
		else:
			print(f"Done: {message}")

	def warning(self, message: str) -> None:
		"""Print a warning message."""
		if self._console:
			self._console.print(f"[yellow]Warning:[/yellow] {message}")
		else:
			print(f"Warning: {message}")

	def print_exception(self) -> None:
		"""Print the current exception."""
		if self._console:
			self._console.print_exception()
		else:
			import traceback

			traceback.print_exc()

	def get_tag_mode(self) -> TagMode:
		"""Return tag mode for process output: colored in dev, plain in ci/prod."""
		return "plain" if self.is_plain else "colored"

	def write_ready_announcement(
		self, address: str, port: int, server_url: str
	) -> None:
		"""Write the 'Pulse is ready' announcement."""
		if self._console:
			self._console.print("")
			self._console.print(
				f"[bold green]Ready:[/bold green] [bold cyan][link={server_url}]{server_url}[/link][/bold cyan]"
			)
			self._console.print("")
		else:
			print("")
			print(f"Ready: {server_url}")
			print("")
		sys.stdout.flush()
