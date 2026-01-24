"""Custom logging configuration for uvicorn to filter noisy requests."""

import logging
from typing import Any, override


class FilterNoisyRequests(logging.Filter):
	"""Filter out noisy requests from uvicorn access logs."""

	# Patterns to suppress (static assets, node_modules, vite internals)
	SUPPRESS_PATTERNS: tuple[str, ...] = (
		"/node_modules/",
		"/@vite/",
		"/%40vite/",  # URL-encoded @vite
		"/@fs/",
		"/%40fs/",  # URL-encoded @fs
		"/@id/",
		"/%40id/",  # URL-encoded @id
		"/@react-refresh",
		"/app/",  # Pulse app files served by Vite
		".js?v=",
		".css?v=",
		".css ",  # CSS files (space indicates end of path in log)
		".tsx ",  # TSX source files
		".ts ",  # TS source files
		".js ",  # JS files
		".map",
		"/favicon.ico",
		"/.well-known/",  # Browser/DevTools well-known endpoints
		"connection open",
		"connection closed",
		"connection rejected",
		"304 Not Modified",  # Usually just cache hits, not interesting
	)

	@override
	def filter(self, record: logging.LogRecord) -> bool:
		"""Return False to suppress log records matching noise patterns."""
		message = record.getMessage()
		# Suppress if message contains any noise pattern
		return not any(pattern in message for pattern in self.SUPPRESS_PATTERNS)


def get_log_config(default_level: str = "info") -> dict[str, Any]:
	"""Get uvicorn logging config with noise filter."""
	return {
		"version": 1,
		"disable_existing_loggers": False,
		"filters": {
			"filter_noisy_requests": {
				"()": "pulse.cli.uvicorn_log_config.FilterNoisyRequests",
			},
		},
		"formatters": {
			"default": {
				"()": "uvicorn.logging.DefaultFormatter",
				"fmt": "%(message)s",
				"use_colors": None,
			},
			"access": {
				"()": "uvicorn.logging.AccessFormatter",
				"fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
			},
		},
		"handlers": {
			"default": {
				"formatter": "default",
				"class": "logging.StreamHandler",
				"stream": "ext://sys.stderr",
			},
			"access": {
				"formatter": "access",
				"class": "logging.StreamHandler",
				"stream": "ext://sys.stdout",
				"filters": ["filter_noisy_requests"],
			},
		},
		"loggers": {
			"uvicorn": {"handlers": ["default"], "level": default_level.upper()},
			"uvicorn.error": {"level": "INFO"},
			"uvicorn.access": {
				"handlers": ["access"],
				"level": "INFO",
				"propagate": False,
			},
		},
	}
