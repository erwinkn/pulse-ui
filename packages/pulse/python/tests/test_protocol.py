import pytest
from pulse.cli.protocol import (
	PREFIX,
	VITE_CONFIGURED,
	WORKER_READY,
	emit,
	parse,
)


def test_emit_and_parse_round_trip(capsys: pytest.CaptureFixture[str]) -> None:
	emit(WORKER_READY)

	lines = capsys.readouterr().out.splitlines()
	assert lines == ["", f"{PREFIX}{WORKER_READY}"]
	assert parse(lines[1]) == (WORKER_READY, "")


def test_parse_marker_embedded_mid_line() -> None:
	assert parse(f"before {PREFIX}{VITE_CONFIGURED} after") == (
		VITE_CONFIGURED,
		"before  after",
	)


def test_parse_unrelated_line_unchanged() -> None:
	line = "ordinary output"
	assert parse(line) == (None, line)
