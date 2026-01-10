"""
Centralized environment variable definitions and typed accessors for Pulse.

Preferred usage:

    from pulse.env import env
    env.pulse_env = "prod"
    if env.running_cli:
        ...

You can still import constants for passing into subprocess env dicts.
"""

from __future__ import annotations

import os
from typing import Literal

# Types
PulseEnv = Literal["dev", "ci", "prod"]

# Keys
ENV_PULSE_ENV = "PULSE_ENV"
ENV_PULSE_APP_FILE = "PULSE_APP_FILE"
ENV_PULSE_APP_DIR = "PULSE_APP_DIR"
ENV_PULSE_HOST = "PULSE_HOST"
ENV_PULSE_PORT = "PULSE_PORT"
ENV_PULSE_REACT_SERVER_ADDRESS = "PULSE_REACT_SERVER_ADDRESS"
ENV_PULSE_BUN_RENDER_SERVER_ADDRESS = "PULSE_BUN_RENDER_SERVER_ADDRESS"
ENV_PULSE_VITE_DEV_SERVER_ADDRESS = "PULSE_VITE_DEV_SERVER_ADDRESS"
ENV_PULSE_SECRET = "PULSE_SECRET"
ENV_PULSE_DISABLE_CODEGEN = "PULSE_DISABLE_CODEGEN"


class EnvVars:
	def _get(self, key: str) -> str | None:
		return os.environ.get(key)

	def _set(self, key: str, value: str | None) -> None:
		if value is None:
			os.environ.pop(key, None)
		else:
			os.environ[key] = value

	@property
	def pulse_env(self) -> PulseEnv:
		value = (self._get(ENV_PULSE_ENV) or "dev").lower()
		if value not in ("dev", "ci", "prod"):
			value = "dev"
		return value

	@pulse_env.setter
	def pulse_env(self, value: PulseEnv) -> None:
		self._set(ENV_PULSE_ENV, value)

	# App file/dir
	@property
	def pulse_app_file(self) -> str | None:
		return self._get(ENV_PULSE_APP_FILE)

	@pulse_app_file.setter
	def pulse_app_file(self, value: str | None) -> None:
		self._set(ENV_PULSE_APP_FILE, value)

	@property
	def pulse_app_dir(self) -> str | None:
		return self._get(ENV_PULSE_APP_DIR)

	@pulse_app_dir.setter
	def pulse_app_dir(self, value: str | None) -> None:
		self._set(ENV_PULSE_APP_DIR, value)

	# Host/port
	@property
	def pulse_host(self) -> str:
		return self._get(ENV_PULSE_HOST) or "localhost"

	@pulse_host.setter
	def pulse_host(self, value: str) -> None:
		self._set(ENV_PULSE_HOST, value)

	@property
	def pulse_port(self) -> int:
		try:
			return int(self._get(ENV_PULSE_PORT) or 8000)
		except Exception:
			return 8000

	@pulse_port.setter
	def pulse_port(self, value: int) -> None:
		self._set(ENV_PULSE_PORT, str(value))

	@property
	def react_server_address(self) -> str | None:
		return self._get(ENV_PULSE_REACT_SERVER_ADDRESS)

	@react_server_address.setter
	def react_server_address(self, value: str | None) -> None:
		self._set(ENV_PULSE_REACT_SERVER_ADDRESS, value)

	@property
	def bun_render_server_address(self) -> str | None:
		return self._get(ENV_PULSE_BUN_RENDER_SERVER_ADDRESS)

	@bun_render_server_address.setter
	def bun_render_server_address(self, value: str | None) -> None:
		self._set(ENV_PULSE_BUN_RENDER_SERVER_ADDRESS, value)

	@property
	def vite_dev_server_address(self) -> str | None:
		return self._get(ENV_PULSE_VITE_DEV_SERVER_ADDRESS)

	@vite_dev_server_address.setter
	def vite_dev_server_address(self, value: str | None) -> None:
		self._set(ENV_PULSE_VITE_DEV_SERVER_ADDRESS, value)

	# Secrets
	@property
	def pulse_secret(self) -> str | None:
		return self._get(ENV_PULSE_SECRET)

	@pulse_secret.setter
	def pulse_secret(self, value: str | None) -> None:
		self._set(ENV_PULSE_SECRET, value)

	# Flags
	@property
	def codegen_disabled(self) -> bool:
		return self._get(ENV_PULSE_DISABLE_CODEGEN) == "1"

	@codegen_disabled.setter
	def codegen_disabled(self, value: bool) -> None:
		self._set(ENV_PULSE_DISABLE_CODEGEN, "1" if value else None)


# Singleton
env = EnvVars()


# Commonly used helpesr
def mode():
	return env.pulse_env
