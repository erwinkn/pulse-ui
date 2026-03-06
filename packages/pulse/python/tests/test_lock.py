from pathlib import Path

from pulse.cli.lock import (
	LockInfo,
	active_lock_info,
	create_lock,
	lock_path_for_web_root,
	read_lock_info,
	remove_lock,
	write_lock_info,
)


def test_create_lock_round_trips_typed_info(tmp_path: Path):
	lock_path = lock_path_for_web_root(tmp_path)

	info = create_lock(lock_path, address="localhost", port=8123)

	assert read_lock_info(lock_path) == info
	assert active_lock_info(lock_path) == info

	remove_lock(lock_path)
	assert read_lock_info(lock_path) is None


def test_active_lock_info_ignores_stale_lock(tmp_path: Path):
	lock_path = lock_path_for_web_root(tmp_path)
	stale = LockInfo(
		pid=999_999,
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
	assert active_lock_info(lock_path) is None
