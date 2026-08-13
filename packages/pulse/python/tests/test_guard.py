from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group behavior")
def test_guard_kills_child_when_stdin_closes(tmp_path: Path) -> None:
	started = tmp_path / "started"
	still = tmp_path / "still"
	child = (
		"import time\n"
		"from pathlib import Path\n"
		f"Path({str(started)!r}).write_text('yes')\n"
		"time.sleep(30)\n"
		f"Path({str(still)!r}).write_text('no')\n"
	)
	process = subprocess.Popen(
		[sys.executable, "-m", "pulse.cli.guard", "--", sys.executable, "-c", child],
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		start_new_session=True,
	)
	assert process.stdin is not None
	deadline = time.monotonic() + 5
	while not started.exists():
		assert time.monotonic() < deadline
		assert process.poll() is None
		time.sleep(0.01)

	process.stdin.close()
	assert process.wait(timeout=5) != 0
	time.sleep(0.2)
	assert not still.exists()
