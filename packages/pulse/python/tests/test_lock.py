import ctypes
import subprocess
import sys
from pathlib import Path

import pytest
from pulse.cli import lock as lock_mod
from pulse.cli.lock import (
	LockInfo,
	active_lock_info,
	create_lock,
	interrupt_active_dev_server,
	is_process_alive,
	lock_path_for_web_root,
	read_lock_info,
	remove_lock,
	write_lock_info,
)


def test_process_liveness_probe_does_not_terminate_live_process():
	proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
	try:
		assert is_process_alive(proc.pid)
		assert proc.poll() is None
	finally:
		proc.terminate()
		proc.wait(timeout=2)

	assert not is_process_alive(proc.pid)


@pytest.mark.parametrize(
	"wait_result",
	[lock_mod.WAIT_OBJECT_0, lock_mod.WAIT_FAILED],
)
def test_windows_interrupt_handles_terminate_race(
	monkeypatch: pytest.MonkeyPatch,
	wait_result: int,
) -> None:
	class Kernel32:
		def OpenProcess(self, access: int, *_args: object) -> int:
			assert access == lock_mod.PROCESS_TERMINATE | lock_mod.PROCESS_SYNCHRONIZE
			return 1

		def TerminateProcess(self, _handle: int, _code: int) -> bool:
			return False

		def WaitForSingleObject(self, _handle: int, _timeout: int) -> int:
			return wait_result

		def CloseHandle(self, _handle: int) -> bool:
			return True

	monkeypatch.setattr(lock_mod, "os_family", lambda: "windows")
	monkeypatch.setattr(lock_mod, "_kernel32", lambda: Kernel32())
	monkeypatch.setattr(
		ctypes,
		"get_last_error",
		lambda: lock_mod.ERROR_ACCESS_DENIED,
		raising=False,
	)

	if wait_result == lock_mod.WAIT_OBJECT_0:
		lock_mod._interrupt_process(123)  # pyright: ignore[reportPrivateUsage]
	else:
		with pytest.raises(RuntimeError, match="Permission denied"):
			lock_mod._interrupt_process(123)  # pyright: ignore[reportPrivateUsage]


def test_create_lock_round_trips_typed_info(tmp_path: Path):
	lock_path = lock_path_for_web_root(tmp_path)

	info = create_lock(lock_path, address="localhost", port=8123)

	assert read_lock_info(lock_path) == info
	assert active_lock_info(tmp_path) == info

	remove_lock(lock_path)
	assert read_lock_info(lock_path) is None


def test_active_lock_info_ignores_stale_lock(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	lock_path = lock_path_for_web_root(tmp_path)

	def process_is_dead(_pid: int) -> bool:
		return False

	monkeypatch.setattr("pulse.cli.lock.is_process_alive", process_is_dead)
	stale = LockInfo(
		pid=123,
		created_at=1,
		hostname="host",
		platform="test-platform",
		python="3.12.0",
		cwd=str(tmp_path),
		address="localhost",
		port=8123,
	)

	write_lock_info(lock_path, stale)

	assert read_lock_info(lock_path) == stale
	assert active_lock_info(tmp_path) is None


def test_interrupt_active_dev_server_stops_live_lock_owner(tmp_path: Path):
	code = f"""
import time
from pathlib import Path
from pulse.cli.lock import FolderLock

web_root = Path({str(tmp_path)!r})
with FolderLock(web_root, address="localhost", port=8123):
	print("ready", flush=True)
	time.sleep(30)
"""
	proc = subprocess.Popen(
		[sys.executable, "-c", code],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)
	try:
		assert proc.stdout is not None
		assert proc.stdout.readline().strip() == "ready"

		info = interrupt_active_dev_server(tmp_path, timeout=2)

		assert info is not None
		assert info.pid == proc.pid
		proc.wait(timeout=2)
		assert active_lock_info(tmp_path) is None
	finally:
		if proc.poll() is None:
			proc.kill()
			proc.wait(timeout=2)
