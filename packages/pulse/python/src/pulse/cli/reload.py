from __future__ import annotations

import argparse
import asyncio
import contextlib
import filecmp
import json
import multiprocessing
import os
import shutil
import signal
import socket
import sys
import tempfile
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, final

import aiohttp
from watchfiles import Change, awatch

from pulse.cli.dev_worker import (
	DEVELOPMENT_GRACEFUL_TIMEOUT,
	WorkerConfig,
	run_generation_worker,
	wait_readable,
)
from pulse.env import ENV_PULSE_VITE_CONTROL_SECRET

IGNORED_DIRECTORIES = frozenset(
	{
		".git",
		".hg",
		".mypy_cache",
		".pytest_cache",
		".ruff_cache",
		".tox",
		".venv",
		"__pycache__",
		"build",
		"dist",
		"node_modules",
		"venv",
	}
)
PYTHON_EXTENSIONS = frozenset({".py", ".pyx", ".pyd"})
VITE_DEADLINE = 10.0
VITE_REQUEST_TIMEOUT = 0.5
VITE_RETRY_DELAY = 0.1


@dataclass(slots=True)
class PulseWatchFilter:
	application_roots: tuple[Path, ...]
	ignored_roots: tuple[Path, ...]
	registered_sources: set[Path] = field(default_factory=set)

	def __post_init__(self) -> None:
		self.application_roots = tuple(
			path.resolve() for path in self.application_roots
		)
		self.ignored_roots = tuple(path.resolve() for path in self.ignored_roots)
		self.registered_sources = {path.resolve() for path in self.registered_sources}

	def add_sources(self, sources: list[str]) -> None:
		self.registered_sources.update(Path(source).resolve() for source in sources)

	def __call__(self, _change: Change, raw_path: str) -> bool:
		path = Path(raw_path).resolve()
		if path in self.registered_sources:
			return True
		if any(part in IGNORED_DIRECTORIES for part in path.parts):
			return False
		if any(
			path == root or path.is_relative_to(root) for root in self.ignored_roots
		):
			return False
		return path.suffix in PYTHON_EXTENSIONS and any(
			path == root or path.is_relative_to(root) for root in self.application_roots
		)


@dataclass(slots=True)
class GenerationWorker:
	generation: int
	process: Any
	control: Any
	stage_path: Path

	def send(self, message_type: str) -> bool:
		try:
			self.control.send({"type": message_type, "generation": self.generation})
		except (BrokenPipeError, EOFError, OSError):
			return False
		return True


async def wait_for_change_or_exit(changed: asyncio.Event, process: Any) -> int | None:
	if not process.is_alive():
		return process.exitcode or 0
	tasks = (
		asyncio.ensure_future(changed.wait()),
		asyncio.ensure_future(wait_readable(process.sentinel)),
	)
	try:
		await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
	finally:
		for task in tasks:
			task.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await task
	if changed.is_set():
		return None
	process.join()
	return process.exitcode or 0


def publish_staged_tree(stage: Path, live: Path) -> list[Path]:
	if not stage.is_dir():
		raise RuntimeError(f"Generation output missing: {stage}")
	live.parent.mkdir(parents=True, exist_ok=True)
	if stage.stat().st_dev != live.parent.stat().st_dev:
		raise RuntimeError("Generation output must be staged on the live filesystem")
	backup = stage.parents[1] / "live-backup"
	backup_temp = backup.with_name("live-backup-preparing")
	if backup.exists():
		_sync_tree(backup, live)
		shutil.rmtree(backup)
	shutil.rmtree(backup_temp, ignore_errors=True)
	if live.is_dir():
		shutil.copytree(live, backup_temp)
	else:
		backup_temp.mkdir(parents=True)
	os.replace(backup_temp, backup)
	try:
		published = _sync_tree(stage, live)
	except BaseException:
		_sync_tree(backup, live)
		shutil.rmtree(backup)
		raise
	else:
		shutil.rmtree(backup)
		shutil.rmtree(stage)
		return sorted(published)


def _sync_tree(source: Path, target: Path) -> set[Path]:
	"""Reconcile a generated tree using atomic per-file replacements."""
	changed: set[Path] = set()
	source_dirs = {
		path.relative_to(source) for path in source.rglob("*") if path.is_dir()
	}
	source_files = {
		path.relative_to(source) for path in source.rglob("*") if path.is_file()
	}
	target_entries = (
		{path.relative_to(target): path for path in target.rglob("*")}
		if target.is_dir()
		else {}
	)

	for relative, path in sorted(
		target_entries.items(), key=lambda item: len(item[0].parts), reverse=True
	):
		if relative not in source_dirs and relative not in source_files:
			if path.is_file() or path.is_symlink():
				changed.add(path)
			elif path.is_dir():
				changed.update(child for child in path.rglob("*") if child.is_file())
			_remove_path(path)
			continue
		if relative in source_dirs and not path.is_dir():
			changed.add(path)
			_remove_path(path)
		elif relative in source_files and not path.is_file():
			if path.is_dir():
				changed.update(child for child in path.rglob("*") if child.is_file())
			_remove_path(path)

	target.mkdir(parents=True, exist_ok=True)
	for relative in sorted(source_dirs, key=lambda path: len(path.parts)):
		(target / relative).mkdir(exist_ok=True)
	for relative in sorted(source_files):
		source_file = source / relative
		target_file = target / relative
		if target_file.is_file() and filecmp.cmp(
			source_file, target_file, shallow=False
		):
			continue
		target_file.parent.mkdir(parents=True, exist_ok=True)
		temporary = target_file.with_name(f".{target_file.name}.pulse-publish")
		shutil.copy2(source_file, temporary)
		os.replace(temporary, target_file)
		changed.add(target_file)
	return changed


def _remove_path(path: Path) -> None:
	if path.is_dir() and not path.is_symlink():
		shutil.rmtree(path)
	else:
		path.unlink(missing_ok=True)


def _cleanup_stale_stages(stage_root: Path) -> None:
	for stale_run in stage_root.glob("run-*"):
		shutil.rmtree(stale_run, ignore_errors=True)
	shutil.rmtree(stage_root / "live-backup-preparing", ignore_errors=True)


@final
class GenerationSupervisor:
	def __init__(
		self,
		*,
		target: str,
		host: str,
		port: int,
		live_path: Path,
		watch_roots: tuple[Path, ...],
		registered_sources: set[Path],
		stage_root: Path,
		vite_port: int | None,
		vite_secret: str | None,
		plain: bool,
		verbose: bool,
	) -> None:
		self.target = target
		self.host = host
		self.port = port
		self.live_path = live_path.resolve()
		self.watch_roots = tuple(path.resolve() for path in watch_roots)
		self.vite_port = vite_port
		self.vite_secret = vite_secret
		self.plain = plain
		self.verbose = verbose
		self.desired = 0
		self.changed = asyncio.Event()
		self.filter = PulseWatchFilter(
			self.watch_roots,
			(self.live_path,),
			registered_sources,
		)
		self._context = multiprocessing.get_context("spawn")
		self.live_path.parent.mkdir(parents=True, exist_ok=True)
		self._stage_parent = stage_root.resolve()
		self._stage_parent.mkdir(parents=True, exist_ok=True)
		if self._stage_parent.stat().st_dev != self.live_path.parent.stat().st_dev:
			raise RuntimeError("Reload staging must use the generated tree filesystem")
		_cleanup_stale_stages(self._stage_parent)
		self._stage_root = Path(tempfile.mkdtemp(prefix="run-", dir=self._stage_parent))
		self.filter.ignored_roots += (self._stage_parent.resolve(),)
		self._listen_socket = self._bind_socket()
		self.active: GenerationWorker | None = None
		self.candidate: GenerationWorker | None = None
		self._announced_ready = False

	def _bind_socket(self) -> socket.socket:
		family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
		sock = socket.socket(family, socket.SOCK_STREAM)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.bind((self.host, self.port))
		sock.listen(2048)
		sock.set_inheritable(True)
		return sock

	async def run(self) -> int:
		watch_task = asyncio.create_task(self._watch())
		self.desired += 1
		self.changed.set()
		try:
			while True:
				if self.active is None:
					await self.changed.wait()
				else:
					exit_code = await wait_for_change_or_exit(
						self.changed, self.active.process
					)
					if exit_code is not None:
						# A dead backend must not tear down the dev session: report
						# it and let the next save spawn a fresh generation.
						print(
							f"Reload error: server exited with code {exit_code}. "
							+ "Waiting for changes to restart...",
							flush=True,
						)
						self._close_worker(self.active)
						self.active = None
						continue
				self.changed.clear()
				generation = self.desired
				self.candidate = self._spawn(generation)
				message = await self._wait_for(self.candidate, {"prepared", "failed"})
				if self.desired != generation:
					self._discard_candidate()
					continue
				if message["type"] == "failed":
					self._report_failure(message)
					self._discard_candidate()
					continue
				if self._add_watch_sources(message.get("sources", [])):
					new_watch_task = asyncio.create_task(self._watch())
					await asyncio.sleep(0)
					watch_task.cancel()
					with contextlib.suppress(asyncio.CancelledError):
						await watch_task
					watch_task = new_watch_task

				preflight = await self._preflight_vite(self.candidate)
				if self.desired != generation:
					self._discard_candidate()
					continue
				if not preflight:
					print(
						"Reload error: Vite is not ready. "
						+ "Waiting for changes to retry...",
						flush=True,
					)
					self._discard_candidate()
					continue

				if self.active is not None:
					await self._drain(self.active)
					self.active = None
				if self.desired != generation:
					self._discard_candidate()
					self.changed.set()
					continue

				if not self.candidate.send("serve"):
					message = self._worker_failure(
						self.candidate, "worker control channel closed"
					)
				else:
					message = await self._wait_for(self.candidate, {"ready", "failed"})
				if self.desired != generation:
					await self._drain(self.candidate)
					self.candidate = None
					self.changed.set()
					continue
				if message["type"] == "failed":
					self._report_failure(message)
					self._discard_candidate()
					continue

				try:
					published_files = publish_staged_tree(
						self.candidate.stage_path, self.live_path
					)
				except Exception as exc:
					# The live tree was restored from backup; the candidate serves
					# code the frontend no longer matches, so retire it and wait.
					print(
						f"Reload error while publishing: {exc}. "
						+ "Waiting for changes to retry...",
						flush=True,
					)
					await self._drain(self.candidate)
					self.candidate = None
					continue
				if self.desired != generation:
					# Publication is the transaction boundary. Finish this commit before
					# preparing a newer generation so Vite and the live tree stay aligned.
					self.changed.set()
				committed = await self._notify_vite(self.candidate, published_files)
				if not committed and self.vite_port is not None:
					# The published tree and backend are consistent; Vite only missed
					# the reload ping. Keep serving — the next commit flushes the
					# files Vite buffered from this publish.
					print(
						f"Reload warning: Vite did not acknowledge generation {generation}; "
						+ "reload the browser manually if it looks stale.",
						flush=True,
					)
				self.active = self.candidate
				self.candidate = None
				if not self._announced_ready:
					self._announced_ready = True
					print("Pulse reload ready", flush=True)
		except (KeyboardInterrupt, asyncio.CancelledError):
			# Shutdown is signal-driven (SIGTERM/SIGINT -> task.cancel()). We
			# swallow the cancellation to return an exit code, which requires
			# uncancel(): otherwise the task still completes as cancelled.
			task = asyncio.current_task()
			if task is not None and task.cancelling():
				task.uncancel()
			return 130
		finally:
			watch_task.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await watch_task
			if self.candidate is not None:
				self._terminate(self.candidate)
				self.candidate = None
			if self.active is not None:
				await self._drain(self.active)
				self.active = None
			self._listen_socket.close()
			shutil.rmtree(self._stage_root, ignore_errors=True)
			with contextlib.suppress(OSError):
				self._stage_parent.rmdir()

	async def _watch(self) -> None:
		async for _changes in awatch(
			*self.watch_roots,
			watch_filter=self.filter,
			debounce=300,
			step=50,
		):
			self.desired += 1
			message = "Changes detected, reloading..."
			if not self.plain:
				message = (
					"\033[1;33mChanges detected,\033[0m \033[1mreloading...\033[0m"
				)
			print(message, flush=True)
			self.changed.set()

	def _add_watch_sources(self, sources: list[str]) -> bool:
		self.filter.add_sources(sources)
		roots = list(self.watch_roots)
		changed = False
		for source in sources:
			parent = Path(source).resolve().parent
			if any(parent == root or parent.is_relative_to(root) for root in roots):
				continue
			roots.append(parent)
			changed = True
		if changed:
			self.watch_roots = tuple(roots)
		return changed

	def _spawn(self, generation: int) -> GenerationWorker:
		stage_path = self._stage_root / f"generation-{generation}"
		shutil.rmtree(stage_path, ignore_errors=True)
		parent, child = self._context.Pipe(duplex=True)
		config = WorkerConfig(
			target=self.target,
			generation=generation,
			stage_path=stage_path,
			host=self.host,
			port=self.port,
			plain=self.plain,
			verbose=self.verbose,
		)
		process = self._context.Process(
			target=run_generation_worker,
			args=(config, child, self._listen_socket),
			name=f"pulse-generation-{generation}",
		)
		process.start()
		child.close()
		return GenerationWorker(generation, process, parent, stage_path)

	async def _wait_for(
		self, worker: GenerationWorker, expected: set[str]
	) -> dict[str, Any]:
		while True:
			if self.desired != worker.generation:
				return {"type": "stale", "generation": worker.generation}
			try:
				has_message = worker.control.poll()
			except (EOFError, OSError):
				return self._worker_failure(worker, "worker control channel closed")
			if has_message:
				try:
					message = worker.control.recv()
				except (EOFError, OSError):
					return self._worker_failure(worker, "worker control channel closed")
				if message.get("generation") != worker.generation:
					continue
				if message.get("type") in expected:
					return message
				continue
			if not worker.process.is_alive():
				return self._worker_failure(
					worker, f"worker exited with code {worker.process.exitcode}"
				)
			await self._wait_for_worker_signal(worker)

	async def _wait_for_worker_signal(self, worker: GenerationWorker) -> None:
		"""Sleep until the worker sends a message, exits, or a file change arrives."""
		try:
			control_fd = worker.control.fileno()
		except OSError:
			# A closed control channel is caught by the caller's next poll().
			return
		tasks = (
			asyncio.ensure_future(self.changed.wait()),
			asyncio.ensure_future(wait_readable(control_fd)),
			asyncio.ensure_future(wait_readable(worker.process.sentinel)),
		)
		try:
			await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
		finally:
			for task in tasks:
				task.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await task

	def _worker_failure(self, worker: GenerationWorker, error: str) -> dict[str, Any]:
		return {
			"type": "failed",
			"generation": worker.generation,
			"phase": "process",
			"error": error,
		}

	async def _drain(self, worker: GenerationWorker) -> None:
		if worker.process.is_alive() and worker.send("drain"):
			with contextlib.suppress(asyncio.TimeoutError):
				await asyncio.wait_for(
					wait_readable(worker.process.sentinel),
					timeout=DEVELOPMENT_GRACEFUL_TIMEOUT + 1,
				)
		await asyncio.to_thread(self._terminate, worker)

	def _terminate(self, worker: GenerationWorker) -> None:
		if worker.process.is_alive():
			worker.process.terminate()
		worker.process.join(timeout=1)
		if worker.process.is_alive():
			worker.process.kill()
			worker.process.join(timeout=1)
		self._close_worker(worker)

	def _close_worker(self, worker: GenerationWorker) -> None:
		with contextlib.suppress(OSError):
			worker.control.close()
		with contextlib.suppress(FileNotFoundError):
			shutil.rmtree(worker.stage_path)

	def _discard_candidate(self) -> None:
		if self.candidate is None:
			return
		self._terminate(self.candidate)
		self.candidate = None

	def _report_failure(self, message: dict[str, Any]) -> None:
		generation = int(message["generation"])
		error = str(message.get("error", "unknown reload failure"))
		print(
			f"Reload error in generation {generation} ({message.get('phase', 'unknown')}): {error}",
			flush=True,
		)
		if details := message.get("traceback"):
			print(details, file=sys.stderr, flush=True)

	async def _preflight_vite(self, worker: GenerationWorker) -> bool:
		if self.vite_port is None or self.vite_secret is None:
			return True
		return await self._race_vite(
			worker,
			self._retry_vite("GET", "/__pulse/health", worker.generation),
			cancel_on_change=True,
		)

	async def _notify_vite(
		self, worker: GenerationWorker, published_files: list[Path]
	) -> bool:
		if self.vite_port is None or self.vite_secret is None:
			return True
		return await self._race_vite(
			worker,
			self._retry_vite(
				"POST",
				"/__pulse/commit",
				worker.generation,
				files=[
					str(path.relative_to(self.live_path)) for path in published_files
				],
			),
			cancel_on_change=False,
		)

	async def _race_vite(
		self,
		worker: GenerationWorker,
		request: Coroutine[Any, Any, bool],
		*,
		cancel_on_change: bool,
	) -> bool:
		request_task = asyncio.ensure_future(request)
		try:
			while not request_task.done():
				watchers: list[asyncio.Task[Any]] = [
					asyncio.ensure_future(wait_readable(worker.process.sentinel))
				]
				if cancel_on_change:
					watchers.append(asyncio.ensure_future(self.changed.wait()))
				try:
					await asyncio.wait(
						[request_task, *watchers],
						return_when=asyncio.FIRST_COMPLETED,
					)
				finally:
					for task in watchers:
						task.cancel()
						with contextlib.suppress(asyncio.CancelledError):
							await task
				if not worker.process.is_alive():
					return False
				if cancel_on_change and self.desired != worker.generation:
					return False
			return request_task.result()
		finally:
			if not request_task.done():
				request_task.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await request_task

	async def _retry_vite(
		self,
		method: str,
		path: str,
		generation: int,
		*,
		files: list[str] | None = None,
	) -> bool:
		assert self.vite_port is not None
		assert self.vite_secret is not None
		url = f"http://localhost:{self.vite_port}{path}"
		headers = {"Authorization": f"Bearer {self.vite_secret}"}
		deadline = time.monotonic() + VITE_DEADLINE
		async with aiohttp.ClientSession() as session:
			while time.monotonic() < deadline:
				remaining = deadline - time.monotonic()
				try:
					async with session.request(
						method,
						url,
						json=(
							{"generation": generation, "files": files or []}
							if method == "POST"
							else None
						),
						headers=headers,
						timeout=aiohttp.ClientTimeout(
							total=min(VITE_REQUEST_TIMEOUT, remaining)
						),
					) as response:
						try:
							body = await response.json()
						except aiohttp.ContentTypeError:
							# Vite is serving but /__pulse endpoints fall through to the
							# SPA handler: the config lacks pulseVitePlugin(). Retrying
							# cannot help, so fail with instructions instead.
							print(
								"Reload error: Vite is running without pulseVitePlugin(). "
								+ "Add it to your Vite config: "
								+ 'import { pulseVitePlugin } from "pulse-ui-client/vite"',
								flush=True,
							)
							return False
						if method == "GET":
							if response.status == 200 and body.get("status") == "ready":
								return True
						elif (
							response.status == 200
							and body.get("status") == "committed"
							and body.get("generation") == generation
						):
							# Fresh commit or an idempotent duplicate (a retry whose
							# original response was lost) — both return this shape.
							return True
						elif response.status == 409 and body.get("status") == "stale":
							# The plugin already committed a newer generation (its 409
							# carries latestGeneration > ours), so this one is
							# superseded and the browser state is at least as fresh.
							return True
						if response.status < 500:
							return False
				except (
					aiohttp.ClientError,
					asyncio.TimeoutError,
					json.JSONDecodeError,
				):
					pass
				await asyncio.sleep(min(VITE_RETRY_DELAY, max(0, remaining)))
		return False


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("--target", required=True)
	parser.add_argument("--host", required=True)
	parser.add_argument("--port", type=int, required=True)
	parser.add_argument("--live-path", type=Path, required=True)
	parser.add_argument("--watch-root", type=Path, action="append", required=True)
	parser.add_argument("--source", type=Path, action="append", default=[])
	parser.add_argument("--stage-root", type=Path, required=True)
	parser.add_argument("--vite-port", type=int)
	parser.add_argument("--plain", action="store_true")
	parser.add_argument("--verbose", action="store_true")
	return parser.parse_args()


async def _run_supervisor(supervisor: GenerationSupervisor) -> int:
	# Cancel the supervisor task from the event loop instead of raising
	# KeyboardInterrupt from a sync signal handler: the raise fires inside loop
	# internals (selector.select) and escapes asyncio.run() before the
	# supervisor's own exception handling can see it.
	loop = asyncio.get_running_loop()
	run_task = asyncio.ensure_future(supervisor.run())
	for signum in (signal.SIGINT, signal.SIGTERM):
		loop.add_signal_handler(signum, run_task.cancel)
	try:
		return await run_task
	finally:
		for signum in (signal.SIGINT, signal.SIGTERM):
			loop.remove_signal_handler(signum)


def main() -> None:
	args = _parse_args()
	# The secret arrives via the environment so it never shows up in `ps` output;
	# pop it so generation workers don't inherit it.
	vite_secret = os.environ.pop(ENV_PULSE_VITE_CONTROL_SECRET, None)
	supervisor = GenerationSupervisor(
		target=args.target,
		host=args.host,
		port=args.port,
		live_path=args.live_path,
		watch_roots=tuple(args.watch_root),
		registered_sources=set(args.source),
		stage_root=args.stage_root,
		vite_port=args.vite_port,
		vite_secret=vite_secret,
		plain=args.plain,
		verbose=args.verbose,
	)
	try:
		raise SystemExit(asyncio.run(_run_supervisor(supervisor)))
	except KeyboardInterrupt:
		# A signal delivered before the loop handlers are installed.
		raise SystemExit(130) from None


if __name__ == "__main__":
	main()
