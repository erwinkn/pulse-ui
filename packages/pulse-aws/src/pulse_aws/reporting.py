"""Lightweight reporting utilities for deployment workflows."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import IO, Literal, Protocol


class Reporter(Protocol):
	"""Simple logging interface to decouple deployment steps from stdout."""

	def section(self, title: str) -> None: ...

	def info(self, message: str) -> None: ...

	def success(self, message: str) -> None: ...

	def warning(self, message: str) -> None: ...

	def detail(self, message: str) -> None: ...

	def blank(self) -> None: ...


class CliReporter:
	"""Human-friendly reporter for interactive CLI runs."""

	def __init__(self, stream: IO[str] | None = None) -> None:
		self._stream: IO[str] = stream or sys.stdout
		self._is_first_section: bool = True

	def section(self, title: str) -> None:
		if not self._is_first_section:
			print("", file=self._stream)
		print(f"=== {title} ===", file=self._stream)
		self._is_first_section = False

	def info(self, message: str) -> None:
		print(message, file=self._stream)

	def success(self, message: str) -> None:
		print(f"[ok] {message}", file=self._stream)

	def warning(self, message: str) -> None:
		print(f"[warn] {message}", file=self._stream)

	def detail(self, message: str) -> None:
		print(f"    {message}", file=self._stream)

	def blank(self) -> None:
		print("", file=self._stream)


class CiReporter:
	"""Minimal reporter suitable for CI logs."""

	def __init__(self, stream: IO[str] | None = None) -> None:
		self._stream: IO[str] = stream or sys.stdout
		self._is_first_section: bool = True

	def section(self, title: str) -> None:
		if not self._is_first_section:
			print("", file=self._stream)
		print(f"## {title}", file=self._stream)
		self._is_first_section = False

	def info(self, message: str) -> None:
		print(message, file=self._stream)

	def success(self, message: str) -> None:
		print(f"SUCCESS: {message}", file=self._stream)

	def warning(self, message: str) -> None:
		print(f"WARNING: {message}", file=self._stream)

	def detail(self, message: str) -> None:
		print(message, file=self._stream)

	def blank(self) -> None:
		print("", file=self._stream)


Mode = Literal["cli", "ci"]


@dataclass(slots=True)
class DeploymentContext:
	"""Deployment execution context shared across helper functions."""

	mode: Mode
	reporter: Reporter
	interactive: bool

	@property
	def ci(self) -> bool:
		return self.mode == "ci"


def detect_mode(default: Mode = "cli") -> Mode:
	"""Detect execution mode via pulse runtime when available."""
	try:
		import pulse as ps  # type: ignore import-not-found
	except ModuleNotFoundError:
		return default
	except Exception:
		return default

	try:
		mode = ps.mode()
	except Exception:
		return default
	return "ci" if str(mode).lower() == "ci" else "cli"


def create_context(
	*,
	mode: Mode | None = None,
	reporter: Reporter | None = None,
	interactive: bool | None = None,
) -> DeploymentContext:
	"""Construct a deployment context with sensible defaults."""
	mode = mode or detect_mode()
	if reporter is None:
		if mode == "ci":
			reporter = CiReporter()
		else:
			reporter = CliReporter()
	if interactive is None:
		interactive = mode != "ci"
	return DeploymentContext(mode=mode, reporter=reporter, interactive=interactive)


__all__ = [
	"CliReporter",
	"CiReporter",
	"DeploymentContext",
	"Reporter",
	"create_context",
	"detect_mode",
]
