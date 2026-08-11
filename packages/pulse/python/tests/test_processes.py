from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import final, override

import pytest
from pulse.cli import processes as process_module
from pulse.cli.models import CommandSpec
from pulse.cli.processes import ManagedProcess


def test_windows_launcher_waits_for_gate_and_preserves_process_contract(
	tmp_path: Path,
) -> None:
	launcher = Path(process_module.__file__).with_name("_windows_launcher.py")
	env = os.environ.copy()
	env["PULSE_LAUNCHER_TEST"] = "environment"
	process = subprocess.Popen(
		[
			sys.executable,
			"-I",
			str(launcher),
			sys.executable,
			"-I",
			"-c",
			(
				"import os, sys; from pathlib import Path; "
				"Path('started').write_text('yes'); "
				"print('|'.join(sys.argv[1:]), flush=True); "
				"print(os.environ['PULSE_LAUNCHER_TEST'], flush=True); "
				"print(sys.stdin.readline().strip(), flush=True); "
				"raise SystemExit(7)"
			),
			"space arg",
			"unicode-ü",
		],
		cwd=tmp_path,
		env=env,
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
	)
	assert process.stdin is not None

	time.sleep(0.1)
	assert process.poll() is None
	assert not (tmp_path / "started").exists()

	process.stdin.write("\0payload\n")
	process.stdin.flush()
	stdout, stderr = process.communicate(timeout=5)

	assert process.returncode == 7
	assert stdout.splitlines() == ["space arg|unicode-ü", "environment", "payload"]
	assert stderr == ""
	assert (tmp_path / "started").read_text() == "yes"


def test_windows_start_assigns_job_before_releasing_launcher(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	events: list[str] = []
	captured: dict[str, object] = {}
	exited = threading.Event()
	exit_codes: list[int] = []

	class Input(io.StringIO):
		@override
		def write(self, value: str) -> int:
			events.append(f"write:{value}")
			return super().write(value)

		@override
		def flush(self) -> None:
			events.append("flush")
			super().flush()

	@final
	class Process:
		pid = 42
		stdin = Input()
		stdout = io.StringIO()

		def wait(self) -> int:
			return 0

		def poll(self) -> int:
			return 0

		def kill(self) -> None:
			return None

	@final
	class Job:
		def __init__(self, _process: object) -> None:
			events.append("assigned")

		def terminate(self) -> None:
			return None

		def close(self) -> None:
			return None

	def popen(args: Sequence[str], **kwargs: object) -> Process:
		events.append("popen")
		captured["args"] = list(args)
		captured.update(kwargs)
		return Process()

	def on_exit(code: int) -> None:
		exit_codes.append(code)
		exited.set()

	monkeypatch.setattr(process_module, "os_family", lambda: "windows")
	monkeypatch.setattr(process_module, "_WindowsJob", Job)
	monkeypatch.setattr(subprocess, "Popen", popen)
	monkeypatch.setattr(
		subprocess,
		"CREATE_NEW_PROCESS_GROUP",
		0x00000200,
		raising=False,
	)

	managed = ManagedProcess.start(
		CommandSpec(
			name="worker",
			args=["target", "space arg"],
			cwd=Path("workdir"),
			env={"KEY": "value"},
		),
		lambda _line: None,
		on_exit,
	)
	assert exited.wait(1)
	managed.close()

	assert events.index("assigned") < events.index("write:\0")
	assert captured["args"] == [
		sys.executable,
		"-I",
		str(Path(process_module.__file__).with_name("_windows_launcher.py")),
		"target",
		"space arg",
	]
	assert captured["creationflags"] == 0x00000200
	assert captured["cwd"] == Path("workdir")
	assert captured["env"] == {"KEY": "value"}
	assert exit_codes == [0]


def test_managed_process_preserves_io_and_target_exit_code(
	tmp_path: Path,
) -> None:
	lines: list[str] = []
	exit_codes: list[int] = []
	exited = threading.Event()

	def on_exit(code: int) -> None:
		exit_codes.append(code)
		exited.set()

	process = ManagedProcess.start(
		CommandSpec(
			name="worker",
			args=[
				sys.executable,
				"-c",
				(
					"import sys; print(sys.stdin.readline().strip(), flush=True); "
					"raise SystemExit(7)"
				),
			],
			cwd=tmp_path,
			env=os.environ.copy(),
		),
		lines.append,
		on_exit,
	)

	process.send_line("payload")
	assert exited.wait(5)
	process.close()

	assert lines == ["payload"]
	assert exit_codes == [7]
	assert process.returncode == 7
