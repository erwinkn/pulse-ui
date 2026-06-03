import subprocess
import sys
from pathlib import Path

import pytest
from pulse.cli.lock import (
	LockInfo,
	active_lock_info,
	create_lock,
	interrupt_active_dev_server,
	lock_path_for_web_root,
	read_lock_info,
	remove_lock,
	write_lock_info,
)


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
