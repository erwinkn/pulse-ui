import asyncio
import os
import pty
from pathlib import Path
from typing import Any, ClassVar, override

from rich.text import Text
from textual.app import App as TextualApp
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container
from textual.events import Key
from textual.widgets import RichLog


class Terminal(RichLog):
	"""A widget that runs a command in a pseudo-terminal."""

	command: list[str]
	cwd: Path | str | None
	env: dict[str, str] | None
	pid: int | None
	fd: int | None

	def __init__(
		self,
		command: list[str],
		cwd: Path | str | None,
		env: dict[str, str] | None = None,
		**kwargs: Any,
	):
		super().__init__(highlight=True, markup=True, wrap=False, **kwargs)
		self.command = command
		self.cwd = cwd
		self.env = env
		self.pid = None
		self.fd = None

	@override
	def on_mount(self) -> None:
		"""Start the command when the widget is mounted."""
		self.pid, self.fd = pty.fork()

		if self.pid == 0:  # Child process
			if self.cwd:
				os.chdir(self.cwd)
			env = os.environ.copy()
			if self.env:
				env.update(self.env)
			os.execvpe(self.command[0], self.command, env)
		else:  # Parent process
			loop = asyncio.get_running_loop()
			loop.add_reader(self.fd, self.read_from_pty)

	def read_from_pty(self) -> None:
		"""Read from the PTY and update the widget."""
		if self.fd is None:
			return
		try:
			data = os.read(self.fd, 1024)
			if not data:
				self.update_log_with_exit_message()
				return
			self.write(Text.from_ansi(data.decode(errors="replace")))
		except OSError:
			self.update_log_with_exit_message()

	def update_log_with_exit_message(self):
		if self.fd:
			asyncio.get_running_loop().remove_reader(self.fd)
			os.close(self.fd)
			self.fd = None
		self.write("\n\n[b red]PROCESS EXITED[/b red]")

	async def on_key(self, event: Key) -> None:
		if self.fd:
			if event.key == "ctrl+c":
				os.write(self.fd, b"\x03")
			else:
				os.write(self.fd, event.key.encode())

	def on_unmount(self) -> None:
		"""Ensure the process is terminated on unmount."""
		if self.pid:
			try:
				os.kill(self.pid, 9)
			except ProcessLookupError:
				pass


class PulseTerminalViewer(TextualApp[None]):
	"""A Textual app to view Pulse server logs in interactive terminals."""

	CSS: ClassVar[str] = """
    Screen {
        background: transparent;
    }
    #main_container {
        layout: horizontal;
        background: transparent;
    }
    Terminal {
        width: 1fr;
        height: 100%;
        margin: 0 1;
        scrollbar-size: 1 1;
    }
    Terminal:focus {
        border: round white;
    }
    #server_term {
        border: round cyan;
    }
    #web_term {
        border: round orange;
    }
    """

	BINDINGS: ClassVar[list[BindingType]] = [
		("q", "quit", "Quit"),
		("ctrl+c", "quit", "Quit"),
	]

	server_command: list[str] | None
	server_cwd: str | Path | None
	server_env: dict[str, str] | None
	web_command: list[str] | None
	web_cwd: str | Path | None
	web_env: dict[str, str] | None

	def __init__(
		self,
		server_command: list[str] | None = None,
		server_cwd: str | Path | None = None,
		server_env: dict[str, str] | None = None,
		web_command: list[str] | None = None,
		web_cwd: str | Path | None = None,
		web_env: dict[str, str] | None = None,
		**kwargs: Any,
	):
		super().__init__(**kwargs)
		self.server_command = server_command
		self.server_cwd = server_cwd
		self.server_env = server_env
		self.web_command = web_command
		self.web_cwd = web_cwd
		self.web_env = web_env

	@override
	def compose(self) -> ComposeResult:
		with Container(id="main_container"):
			if self.server_command:
				server_term = Terminal(
					self.server_command,
					self.server_cwd,
					self.server_env,
					id="server_term",
				)
				server_term.border_title = "🐍 Python Server"
				yield server_term

			if self.web_command:
				web_term = Terminal(
					self.web_command, self.web_cwd, self.web_env, id="web_term"
				)
				web_term.border_title = "🌐 Web Server"
				yield web_term
