from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence


def main(args: Sequence[str]) -> int:
	if os.read(sys.stdin.fileno(), 1) != b"\0":
		return 1
	if not args:
		return 1

	if hasattr(signal, "SIGBREAK"):
		signal.signal(signal.SIGBREAK, lambda _signum, _frame: None)

	process = subprocess.Popen(
		args,
		stdin=sys.stdin,
		stdout=sys.stdout,
		stderr=sys.stderr,
	)
	return process.wait()


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
