from __future__ import annotations

import asyncio
import socket

import pytest
from pulse.cli.relay import TcpRelay, reserve_port


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


@pytest.mark.asyncio
async def test_tcp_relay_keeps_its_port_while_retargeting() -> None:
	loop = asyncio.get_running_loop()
	loop_errors: list[dict[str, object]] = []
	previous_handler = loop.get_exception_handler()
	loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

	async def target(
		prefix: bytes,
		reader: asyncio.StreamReader,
		writer: asyncio.StreamWriter,
	) -> None:
		writer.write(prefix + await reader.read())
		await writer.drain()
		writer.close()
		await writer.wait_closed()

	async def request(port: int, body: bytes) -> bytes:
		reader, writer = await asyncio.open_connection("127.0.0.1", port)
		writer.write(body)
		await writer.drain()
		writer.write_eof()
		response = await reader.read()
		writer.close()
		await writer.wait_closed()
		return response

	first = await asyncio.start_server(
		lambda reader, writer: target(b"first:", reader, writer),
		"127.0.0.1",
		0,
	)
	second = await asyncio.start_server(
		lambda reader, writer: target(b"second:", reader, writer),
		"127.0.0.1",
		0,
	)
	reservation = reserve_port("127.0.0.1", 0, find_port=False)
	relay = TcpRelay(reservation)
	await relay.start()
	try:
		first_port = first.sockets[0].getsockname()[1]
		second_port = second.sockets[0].getsockname()[1]
		relay.set_target("127.0.0.1", first_port)
		assert await request(relay.port, b"one") == b"first:one"
		_reader, disconnected = await asyncio.open_connection("127.0.0.1", relay.port)
		disconnected.write(b"gone")
		await disconnected.drain()
		disconnected.close()
		await disconnected.wait_closed()
		await asyncio.sleep(0.01)
		relay.clear_target()
		held_reader, held_writer = await asyncio.open_connection(
			"127.0.0.1", relay.port
		)
		held_writer.write(b"held")
		await held_writer.drain()
		held_writer.write_eof()
		held = asyncio.create_task(held_reader.read())
		await asyncio.sleep(0.05)
		assert not held.done()
		relay.set_target("127.0.0.1", second_port)
		assert await asyncio.wait_for(held, timeout=2) == b"second:held"
		held_writer.close()
		await held_writer.wait_closed()
		assert await request(relay.port, b"two") == b"second:two"
	finally:
		await relay.close()
		first.close()
		second.close()
		await first.wait_closed()
		await second.wait_closed()
		loop.set_exception_handler(previous_handler)
	assert loop_errors == []


@pytest.mark.asyncio
async def test_tcp_relay_holds_connections_until_a_target_appears() -> None:
	async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
		writer.write(b"echo:" + await reader.read())
		await writer.drain()
		writer.close()
		await writer.wait_closed()

	backend = await asyncio.start_server(echo, "127.0.0.1", 0)
	reservation = reserve_port("127.0.0.1", 0, find_port=False)
	relay = TcpRelay(reservation)
	await relay.start()
	try:
		# Connect during a restart window: no target yet.
		reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
		writer.write(b"held")
		await writer.drain()
		writer.write_eof()
		await asyncio.sleep(0.05)
		relay.set_target("127.0.0.1", backend.sockets[0].getsockname()[1])
		assert await asyncio.wait_for(reader.read(), timeout=2) == b"echo:held"
		writer.close()
		await writer.wait_closed()
	finally:
		await relay.close()
		backend.close()
		await backend.wait_closed()
