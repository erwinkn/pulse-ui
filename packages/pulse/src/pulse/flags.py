from contextvars import ContextVar


IS_PRERENDERING: ContextVar[bool] = ContextVar("pulse_is_prerendering", default=False)
