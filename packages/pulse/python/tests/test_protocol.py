import sys

import pytest
from pulse.cli.protocol import (
	PREFIX,
	VITE_CONFIGURED,
	VITE_LISTENING,
	WORKER_READY,
	emit,
	parse,
)


def test_emit_and_parse_round_trip(capsys: pytest.CaptureFixture[str]) -> None:
	emit(WORKER_READY)

	lines = capsys.readouterr().out.splitlines()
	assert lines == ["", f"{PREFIX}{WORKER_READY}"]
	assert parse(lines[1]) == ([WORKER_READY], "")


def test_parse_marker_embedded_mid_line() -> None:
	assert parse(f"before {PREFIX}{VITE_CONFIGURED} after") == (
		[VITE_CONFIGURED],
		"before  after",
	)


def test_parse_multiple_markers_on_one_line() -> None:
	line = f"a{PREFIX}{VITE_CONFIGURED}{PREFIX}{VITE_LISTENING}b"
	assert parse(line) == ([VITE_CONFIGURED, VITE_LISTENING], "ab")


def test_parse_unknown_marker_left_intact() -> None:
	line = f"before {PREFIX}unknown after"
	assert parse(line) == ([], line)


def test_parse_unrelated_line_unchanged() -> None:
	line = "ordinary output"
	assert parse(line) == ([], line)


def test_emit_survives_closed_stdout(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class ClosedStream:
		def write(self, _text: str) -> int:
			raise BrokenPipeError

		def flush(self) -> None:
			raise BrokenPipeError

	monkeypatch.setattr(sys, "stdout", ClosedStream())
	emit(WORKER_READY)
