from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from typing import (
    Awaitable,
    Callable,
    Optional,
    Unpack,
    TYPE_CHECKING,
)

from fastapi import UploadFile
from starlette.datastructures import FormData as StarletteFormData

from .context import PulseContext
from .html import HTMLFormProps, form
from .vdom import Child

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .app import App


FormValue = str | UploadFile
FormData = dict[str, FormValue | list[FormValue]]

__all__ = ["Form", "FormData", "UploadFile"]


@dataclass(slots=True)
class FormRegistration:
    """Internal metadata stored for each registered form."""

    id: str
    render_id: str
    route_path: str
    session_id: str
    on_submit: Callable[[FormData], None | Awaitable[None]]


def normalize_form_data(raw: StarletteFormData) -> FormData:
    """Convert Starlette FormData into a dict keeping UploadFiles intact."""

    normalized: FormData = {}
    # multi_items() preserves duplicates while decoding percent-encoded keys
    for key, value in raw.multi_items():
        item: FormValue
        if isinstance(value, UploadFile):
            item = value
        else:
            item = str(value)

        existing = normalized.get(key)
        if existing is None:
            normalized[key] = item
        elif isinstance(existing, list):
            existing.append(item)
        else:
            normalized[key] = [existing, item]

    return normalized


class Form:
    def __init__(self, on_submit: Callable[[FormData], None | Awaitable[None]]) -> None:
        ctx = PulseContext.get()
        render = ctx.render
        route = ctx.route
        session = ctx.session

        if render is None:
            raise RuntimeError("ps.Form() must be created during a render pass")
        if route is None:
            raise RuntimeError("ps.Form() requires an active route context")
        if session is None:
            raise RuntimeError("ps.Form() requires an active user session")

        self._app: App = ctx.app
        self._render_id = render.id
        self._route_path = route.pathname
        self._session_id = session.sid
        self._id = uuid.uuid4().hex
        self._disposed = False

        registration = FormRegistration(
            id=self._id,
            render_id=self._render_id,
            route_path=self._route_path,
            session_id=self._session_id,
            on_submit=on_submit,
        )
        self._app._register_form(registration)

    @property
    def id(self) -> str:
        return self._id

    def __call__(
        self,
        *children: Child,
        key: Optional[str] = None,
        **props: Unpack[HTMLFormProps],
    ):
        props = props | self.props()
        return form(*children, key=key, **props)

    def props(self) -> HTMLFormProps:
        if self._disposed:
            raise RuntimeError("Cannot access props on a disposed form")
        self._app._mark_form_used(self._render_id, self._route_path, self._id)
        return {
            "action": f"/pulse/forms/{self._id}",
            "method": "POST",
            "encType": "multipart/form-data",
        }

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._app._unregister_form(self._id)


async def call_form_handler(handler: Callable[[FormData], None | Awaitable[None]], data: FormData):
    """Invoke the form handler, awaiting if necessary."""

    maybe = handler(data)
    if inspect.isawaitable(maybe):
        await maybe
