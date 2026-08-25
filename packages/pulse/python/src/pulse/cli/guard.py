"""Exit the wrapped command when the supervisor's stdin pipe closes.

This POSIX watchdog intentionally remains separate from _windows_launcher,
which owns Windows' suspended-start handshake and Job Object setup.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading


def main() -> int:
	if "--" not in sys.argv:
		print("usage: python -m pulse.cli.guard -- command [args...]", file=sys.stderr)
		return 2
	args = sys.argv[sys.argv.index("--") + 1 :]
	if not args:
		return 2
	process = subprocess.Popen(
		args,
		stdin=subprocess.DEVNULL,
		close_fds=False,
	)

	def on_eof() -> None:
		sys.stdin.read()
		if process.poll() is not None:
			return
		if os.name == "nt":
			process.terminate()
			try:
				process.wait(timeout=1)
			except subprocess.TimeoutExpired:
				process.kill()
			return
		with contextlib.suppress(ProcessLookupError, PermissionError):
			os.killpg(os.getpgid(process.pid), signal.SIGKILL)

	threading.Thread(target=on_eof, daemon=True, name="pulse-guard").start()
	return process.wait()


if __name__ == "__main__":
	raise SystemExit(main())
