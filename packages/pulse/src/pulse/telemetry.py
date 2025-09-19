from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Optional
from .context import PulseContext


class Span:
    def __init__(
        self,
        telemetry: "Telemetry",
        name: str,
        attributes: Optional[dict[str, Any]] = None,
    ):
        self.telemetry = telemetry
        self.name = name
        self.attributes = attributes or {}
        self._t0 = perf_counter()
        self._ended = False

    def end(self, **extra_attrs: Any) -> None:
        if self._ended:
            return
        self._ended = True
        duration_ms = (perf_counter() - self._t0) * 1000.0
        attrs = dict(self.attributes)
        if extra_attrs:
            attrs.update(extra_attrs)
        self.telemetry.observe(self.name, duration_ms, attrs)

    # Support context manager pattern
    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        status = "error" if exc is not None else "ok"
        self.end(status=status)


class Telemetry:
    def incr(self, name: str, labels: Optional[dict[str, str]] = None) -> None:
        raise NotImplementedError

    def observe(
        self, name: str, value_ms: float, attributes: Optional[dict[str, Any]] = None
    ) -> None:
        raise NotImplementedError

    def start_span(
        self, name: str, attributes: Optional[dict[str, Any]] = None
    ) -> Span:
        return Span(self, name, attributes)

    @contextmanager
    def measure(self, name: str, attributes: Optional[dict[str, Any]] = None):
        span = self.start_span(name, attributes)
        try:
            yield span
        finally:
            span.end()


def telemetry():
    return PulseContext.get().app.telemetry


class NoopTelemetry(Telemetry):
    def incr(self, name: str, labels: Optional[dict[str, str]] = None) -> None:
        return None

    def observe(
        self, name: str, value_ms: float, attributes: Optional[dict[str, Any]] = None
    ) -> None:
        return None


@dataclass
class LoggerTelemetry(Telemetry):
    """Very lightweight logger-based telemetry for basic visibility.

    Emits to Python logging at DEBUG level. Suitable for early wiring without
    pulling in metrics backends.
    """

    logger: Any

    def incr(self, name: str, labels: Optional[dict[str, str]] = None) -> None:
        try:
            self.logger.debug("telemetry.incr name=%s labels=%s", name, labels or {})
        except Exception:
            pass

    def observe(
        self, name: str, value_ms: float, attributes: Optional[dict[str, Any]] = None
    ) -> None:
        try:
            self.logger.debug(
                "telemetry.observe name=%s value_ms=%.3f attrs=%s",
                name,
                value_ms,
                attributes or {},
            )
        except Exception:
            pass


def telemetry_from_env(mode: str, logger: Any) -> Telemetry:
    """Factory based on env value.

    mode: "off" | "basic" | "detailed" | "trace"
    For now, we only distinguish off vs basic (logger). Others can map to basic.
    """
    m = (mode or "off").lower()
    if m == "off":
        return NoopTelemetry()
    # Future: return Prometheus or OTEL exporters for detailed/trace
    return LoggerTelemetry(logger=logger)


__all__ = [
    "Telemetry",
    "Span",
    "NoopTelemetry",
    "LoggerTelemetry",
    "telemetry_from_env",
]
