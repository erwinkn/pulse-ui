from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import socket
from dataclasses import dataclass
from typing import final

# How long the relay waits for the private backend to accept a connection
# after a target is selected. Waiters for a missing target stay parked until
# set_target or close — first start and failed imports should not drop clients.
RELAY_CONNECT_TIMEOUT = 2.0


@dataclass(slots=True)
class PortReservation:
	port: int
	sockets: tuple[socket.socket, ...]

	def close(self) -> None:
		for listener in self.sockets:
			with contextlib.suppress(OSError):
				listener.close()


def reserve_port(
	host: str,
	start_port: int,
	*,
	find_port: bool,
	max_attempts: int = 100,
) -> PortReservation:
	"""Atomically select and retain the first bindable TCP port."""
	attempts = max_attempts if find_port else 1
	last_error: OSError | None = None
	for port in range(start_port, start_port + attempts):
		try:
			bound_port, listeners = _bind_port(host, port)
		except OSError as exc:
			last_error = exc
			if exc.errno == errno.EADDRINUSE and find_port:
				continue
			raise RuntimeError(f"Cannot bind {host}:{port}: {exc}") from exc
		return PortReservation(bound_port, listeners)
	raise RuntimeError(
		f"No available port found from {start_port} to {start_port + attempts - 1}"
	) from last_error


def _bind_port(host: str, port: int) -> tuple[int, tuple[socket.socket, ...]]:
	targets = _bind_targets(host)
	listeners: list[socket.socket] = []
	bound_port = port
	try:
		for family, address, optional in targets:
			listener = socket.socket(family, socket.SOCK_STREAM)
			try:
				if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
					listener.setsockopt(
						socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
					)
				else:
					listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
				if family == socket.AF_INET6:
					listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
				listener.bind((address, bound_port))
				if bound_port == 0:
					bound_port = listener.getsockname()[1]
				listener.listen(socket.SOMAXCONN)
				listener.setblocking(False)
			except OSError as exc:
				listener.close()
				if optional and exc.errno in (
					errno.EAFNOSUPPORT,
					errno.EADDRNOTAVAIL,
					errno.EPROTONOSUPPORT,
				):
					continue
				raise
			listeners.append(listener)
		if not listeners:
			raise OSError(errno.EADDRNOTAVAIL, f"No address available for {host}")
		return bound_port, tuple(listeners)
	except BaseException:
		for listener in listeners:
			listener.close()
		raise


def _bind_targets(host: str) -> tuple[tuple[socket.AddressFamily, str, bool], ...]:
	if host == "localhost":
		return (
			(socket.AF_INET, "127.0.0.1", False),
			(socket.AF_INET6, "::1", True),
		)
	addresses: list[tuple[socket.AddressFamily, str, bool]] = []
	for family, _type, _proto, _canonname, address in socket.getaddrinfo(
		host,
		None,
		type=socket.SOCK_STREAM,
		flags=socket.AI_PASSIVE,
	):
		if family not in (socket.AF_INET, socket.AF_INET6):
			continue
		if not isinstance(address[0], str):
			continue
		target = (family, address[0], False)
		if target not in addresses:
			addresses.append(target)
	return tuple(addresses)


@final
class TcpRelay:
	"""Long-lived TCP listener whose private target can change between workers."""

	def __init__(self, reservation: PortReservation) -> None:
		self._reservation = reservation
		self._servers: list[asyncio.Server] = []
		self._connections: set[asyncio.Task[None]] = set()
		self._target: tuple[str, int] | None = None
		self._target_set = asyncio.Event()
		self._closed = False

	@property
	def port(self) -> int:
		return self._reservation.port

	@property
	def target(self) -> tuple[str, int] | None:
		return self._target

	def set_target(self, host: str, port: int) -> None:
		if self._closed:
			return
		self._target = (host, port)
		self._target_set.set()

	def clear_target(self) -> None:
		self._target = None
		self._target_set.clear()

	async def start(self) -> None:
		if self._servers:
			raise RuntimeError("TCP relay is already running")
		for listener in self._reservation.sockets:
			self._servers.append(
				await asyncio.start_server(self._accept, sock=listener)
			)

	async def close(self) -> None:
		self._closed = True
		self._target = None
		self._target_set.set()
		for server in self._servers:
			server.close()
		for server in self._servers:
			await server.wait_closed()
		self._servers.clear()
		for task in self._connections:
			task.cancel()
		if self._connections:
			await asyncio.gather(*self._connections, return_exceptions=True)
		self._reservation.close()

	async def _accept(
		self,
		client_reader: asyncio.StreamReader,
		client_writer: asyncio.StreamWriter,
	) -> None:
		task = asyncio.current_task()
		if task is not None:
			self._connections.add(task)
		try:
			sock = client_writer.get_extra_info("socket")
			if sock is not None:
				with contextlib.suppress(OSError):
					sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
			target = await self._wait_for_target()
			if target is None:
				return
			try:
				target_reader, target_writer = await asyncio.wait_for(
					asyncio.open_connection(*target),
					timeout=RELAY_CONNECT_TIMEOUT,
				)
			except (OSError, TimeoutError):
				return
			try:
				upstream = asyncio.create_task(self._copy(client_reader, target_writer))
				downstream = asyncio.create_task(
					self._copy(target_reader, client_writer)
				)
				pipes = (upstream, downstream)
				try:
					await asyncio.gather(*pipes)
				except OSError:
					pass
				finally:
					for pipe in pipes:
						pipe.cancel()
					await asyncio.gather(*pipes, return_exceptions=True)
			finally:
				target_writer.close()
				with contextlib.suppress(OSError):
					await target_writer.wait_closed()
		finally:
			client_writer.close()
			with contextlib.suppress(OSError):
				await client_writer.wait_closed()
			if task is not None:
				self._connections.discard(task)

	async def _wait_for_target(self) -> tuple[str, int] | None:
		while not self._closed and self._target is None:
			await self._target_set.wait()
			if self._target is None and not self._closed and self._target_set.is_set():
				self._target_set.clear()
		if self._closed:
			return None
		return self._target

	@staticmethod
	async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
		while data := await reader.read(64 * 1024):
			writer.write(data)
			await writer.drain()
		if writer.can_write_eof():
			with contextlib.suppress(OSError):
				writer.write_eof()
				await writer.drain()
