from __future__ import annotations

import socket

import pytest
from pulse.cli.ports import reserve_port


def test_reserve_port_selects_and_holds_first_available_port() -> None:
	occupied = socket.socket()
	occupied.bind(("127.0.0.1", 0))
	occupied.listen()
	start_port = occupied.getsockname()[1]
	reservation = reserve_port("127.0.0.1", start_port, find_port=True)
	try:
		assert reservation.port > start_port
		second = socket.socket()
		try:
			with pytest.raises(OSError):
				second.bind(("127.0.0.1", reservation.port))
		finally:
			second.close()
	finally:
		reservation.close()
		occupied.close()


def test_reserve_port_exact_mode_fails_when_occupied() -> None:
	occupied = socket.socket()
	occupied.bind(("127.0.0.1", 0))
	occupied.listen()
	try:
		with pytest.raises(RuntimeError, match="Cannot bind"):
			reserve_port("127.0.0.1", occupied.getsockname()[1], find_port=False)
	finally:
		occupied.close()


def test_ephemeral_reservation_reports_actual_port() -> None:
	reservation = reserve_port("127.0.0.1", 0, find_port=False)
	try:
		assert reservation.port == reservation.sockets[0].getsockname()[1]
		assert reservation.port > 0
	finally:
		reservation.close()
