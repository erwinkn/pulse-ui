"""Browser navigator global object.

Usage:
    from pulse.js2 import navigator, console
    console.log(navigator.userAgent)
"""

from typing import Any as _Any

from pulse.js2._types import Clipboard as _Clipboard
from pulse.transpiler_v2.js_module import JsModule

# User agent and browser info
userAgent: str
language: str
languages: list[str]
platform: str
vendor: str
appName: str
appVersion: str

# Online status
onLine: bool

# Hardware info
hardwareConcurrency: int
maxTouchPoints: int
deviceMemory: float | None  # May not be available in all browsers

# Cookies
cookieEnabled: bool

# PDF viewer
pdfViewerEnabled: bool

# Clipboard API
clipboard: _Clipboard

# Media devices (typed as _Any for simplicity)
mediaDevices: _Any

# Permissions (typed as _Any for simplicity)
permissions: _Any

# Service worker (typed as _Any for simplicity)
serviceWorker: _Any

# Geolocation (typed as _Any for simplicity)
geolocation: _Any

# Storage
storage: _Any


# Methods
def vibrate(pattern: int | list[int]) -> bool:
	"""Vibrate the device. Returns True if vibration is supported."""
	...


def share(data: dict[str, str]) -> _Any:
	"""Share data via the Web Share API. Returns a Promise."""
	...


def sendBeacon(url: str, data: str | bytes | _Any | None = None) -> bool:
	"""Send data to a URL asynchronously. Returns True if successful."""
	...


def canShare(data: dict[str, str] | None = None) -> bool:
	"""Check if data can be shared via the Web Share API."""
	...


JsModule.register(name="navigator")
