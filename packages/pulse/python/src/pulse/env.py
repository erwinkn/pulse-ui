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
"""Environment type for the Pulse application.

Values:
    "dev": Development environment with hot reload and debugging.
    "ci": Continuous integration environment for testing.
    "prod": Production environment with optimizations enabled.
"""

# Keys
ENV_PULSE_ENV = "PULSE_ENV"
ENV_PULSE_APP_FILE = "PULSE_APP_FILE"
ENV_PULSE_APP_DIR = "PULSE_APP_DIR"
ENV_PULSE_HOST = "PULSE_HOST"
ENV_PULSE_PORT = "PULSE_PORT"
ENV_PULSE_REACT_SERVER_ADDRESS = "PULSE_REACT_SERVER_ADDRESS"
ENV_PULSE_SECRET = "PULSE_SECRET"
ENV_PULSE_DISABLE_CODEGEN = "PULSE_DISABLE_CODEGEN"
ENV_PULSE_HOT_RELOAD = "PULSE_HOT_RELOAD"
ENV_PULSE_HOT_RELOAD_DIRS = "PULSE_HOT_RELOAD_DIRS"
ENV_PULSE_HOT_RELOAD_EXCLUDES = "PULSE_HOT_RELOAD_EXCLUDES"
ENV_PULSE_HOT_RELOAD_TRIGGER = "PULSE_HOT_RELOAD_TRIGGER"


class EnvVars:
	"""Singleton accessor for Pulse environment variables.

	Provides typed getters and setters for all Pulse-related environment
	variables. Access via the `env` singleton instance.

	Example:
		```python
		from pulse.env import env

		env.pulse_env = "prod"
		if env.pulse_env == "dev":
		    print(f"Running on {env.pulse_host}:{env.pulse_port}")
		```

	Attributes:
		pulse_env: Current environment ("dev", "ci", "prod").
		pulse_host: Server hostname. Defaults to "localhost".
		pulse_port: Server port number. Defaults to 8000.
		pulse_secret: Secret key for JWT session signing.
		codegen_disabled: If True, skip code generation.
	"""

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

	@property
	def pulse_hot_reload(self) -> bool:
		value = self._get(ENV_PULSE_HOT_RELOAD)
		if value is None:
			return self.pulse_env == "dev"
		return value not in ("0", "false", "False")

	@pulse_hot_reload.setter
	def pulse_hot_reload(self, value: bool) -> None:
		self._set(ENV_PULSE_HOT_RELOAD, "1" if value else "0")

	@property
	def pulse_hot_reload_dirs(self) -> list[str]:
		raw = self._get(ENV_PULSE_HOT_RELOAD_DIRS)
		if not raw:
			return []
		return [p for p in raw.split(os.pathsep) if p]

	@pulse_hot_reload_dirs.setter
	def pulse_hot_reload_dirs(self, value: list[str]) -> None:
		if not value:
			self._set(ENV_PULSE_HOT_RELOAD_DIRS, None)
			return
		self._set(ENV_PULSE_HOT_RELOAD_DIRS, os.pathsep.join(value))

	@property
	def pulse_hot_reload_excludes(self) -> list[str]:
		raw = self._get(ENV_PULSE_HOT_RELOAD_EXCLUDES)
		if not raw:
			return []
		return [p for p in raw.split(os.pathsep) if p]

	@pulse_hot_reload_excludes.setter
	def pulse_hot_reload_excludes(self, value: list[str]) -> None:
		if not value:
			self._set(ENV_PULSE_HOT_RELOAD_EXCLUDES, None)
			return
		self._set(ENV_PULSE_HOT_RELOAD_EXCLUDES, os.pathsep.join(value))

	@property
	def pulse_hot_reload_trigger(self) -> str | None:
		return self._get(ENV_PULSE_HOT_RELOAD_TRIGGER)

	@pulse_hot_reload_trigger.setter
	def pulse_hot_reload_trigger(self, value: str | None) -> None:
		self._set(ENV_PULSE_HOT_RELOAD_TRIGGER, value)


# Singleton
env = EnvVars()
"""Singleton instance for accessing Pulse environment variables.

Example:
    ```python
    from pulse.env import env

    env.pulse_env = "prod"
    print(env.pulse_host)  # "localhost"
    print(env.pulse_port)  # 8000
    ```
"""


def mode() -> PulseEnv:
	"""Returns the current pulse_env value.

	Shorthand for `env.pulse_env`.

	Returns:
		The current environment: "dev", "ci", or "prod".

	Example:
		```python
		from pulse.env import mode

		if mode() == "dev":
		    enable_debug_toolbar()
		```
	"""
	return env.pulse_env
