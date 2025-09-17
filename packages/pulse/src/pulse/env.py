"""
Centralized environment variable definitions and typed accessors for Pulse.

Preferred usage:

    from pulse.env import env
    env.pulse_mode = "prod"
    if env.running_cli:
        ...

You can still import constants for passing into subprocess env dicts.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

# Types
PulseMode = Literal["dev", "ci", "prod"]

# Keys
ENV_PULSE_MODE = "PULSE_MODE"
ENV_PULSE_APP_FILE = "PULSE_APP_FILE"
ENV_PULSE_APP_DIR = "PULSE_APP_DIR"
ENV_PULSE_HOST = "PULSE_HOST"
ENV_PULSE_PORT = "PULSE_PORT"
ENV_PULSE_SECRET = "PULSE_SECRET"
ENV_PULSE_LOCK_MANAGED_BY_CLI = "PULSE_LOCK_MANAGED_BY_CLI"
ENV_PULSE_DISABLE_CODEGEN = "PULSE_DISABLE_CODEGEN"


class Env:
    def _get(self, key: str) -> Optional[str]:
        return os.environ.get(key)

    def _set(self, key: str, value: Optional[str]) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    # Pulse mode
    @property
    def pulse_mode(self) -> PulseMode:
        value = (self._get(ENV_PULSE_MODE) or "dev").lower()
        if value not in ("dev", "ci", "prod"):
            value = "dev"
        return value  # type: ignore[return-value]

    @pulse_mode.setter
    def pulse_mode(self, value: PulseMode) -> None:
        self._set(ENV_PULSE_MODE, value)

    # App file/dir
    @property
    def pulse_app_file(self) -> Optional[str]:
        return self._get(ENV_PULSE_APP_FILE)

    @pulse_app_file.setter
    def pulse_app_file(self, value: Optional[str]) -> None:
        self._set(ENV_PULSE_APP_FILE, value)

    @property
    def pulse_app_dir(self) -> Optional[str]:
        return self._get(ENV_PULSE_APP_DIR)

    @pulse_app_dir.setter
    def pulse_app_dir(self, value: Optional[str]) -> None:
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

    # Secrets
    @property
    def pulse_secret(self) -> Optional[str]:
        return self._get(ENV_PULSE_SECRET)

    @pulse_secret.setter
    def pulse_secret(self, value: Optional[str]) -> None:
        self._set(ENV_PULSE_SECRET, value)

    # Flags
    @property
    def lock_managed_by_cli(self) -> bool:
        return self._get(ENV_PULSE_LOCK_MANAGED_BY_CLI) == "1"

    @lock_managed_by_cli.setter
    def lock_managed_by_cli(self, value: bool) -> None:
        self._set(ENV_PULSE_LOCK_MANAGED_BY_CLI, "1" if value else None)

    @property
    def codegen_disabled(self) -> bool:
        return self._get(ENV_PULSE_DISABLE_CODEGEN) == "1"

    @codegen_disabled.setter
    def codegen_disabled(self, value: bool) -> None:
        self._set(ENV_PULSE_DISABLE_CODEGEN, "1" if value else None)


# Singleton
env = Env()
