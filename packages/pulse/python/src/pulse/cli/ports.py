from __future__ import annotations

import contextlib
import errno
import os
import socket
from dataclasses import dataclass


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
	"""Bind and keep the first available TCP port."""
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
				listener.set_inheritable(True)
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
