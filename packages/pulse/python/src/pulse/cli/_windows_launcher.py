"""Release a Windows child after the supervisor assigns its Job Object.

This suspended-start handshake intentionally remains separate from guard,
which is a POSIX stdin watchdog with opposite stdin ownership.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence

HANDSHAKE_FAILURE_EXIT_CODE = 125


def main(args: Sequence[str]) -> int:
	if not args:
		return 1

	try:
		gate = os.read(sys.stdin.fileno(), 1)
	except OSError as exc:
		print(f"pulse Windows launcher handshake failed: {exc}", file=sys.stderr)
		return HANDSHAKE_FAILURE_EXIT_CODE
	if gate != b"\0":
		print(
			"pulse Windows launcher handshake failed: expected supervisor gate",
			file=sys.stderr,
		)
		return HANDSHAKE_FAILURE_EXIT_CODE

	if hasattr(signal, "SIGBREAK"):
		signal.signal(signal.SIGBREAK, lambda _signum, _frame: None)

	process = subprocess.Popen(
		args,
		stdin=sys.stdin,
		stdout=sys.stdout,
		stderr=sys.stderr,
		close_fds=False,
	)
	return process.wait()


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
