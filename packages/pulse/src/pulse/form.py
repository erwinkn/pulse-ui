from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Never,
    Optional,
    TypedDict,
    Unpack,
)

from fastapi import HTTPException, Request, Response
from starlette.datastructures import FormData as StarletteFormData
from starlette.datastructures import UploadFile

from pulse.helpers import call_flexible, maybe_await
from pulse.reactive import Signal
from pulse.serializer import deserialize
from pulse.types.event_handler import EventHandler1

from pulse.context import PulseContext
from pulse.hooks.core import HOOK_CONTEXT
from pulse.hooks.runtime import server_address
from pulse.hooks.stable import stable
from pulse.hooks.forms import internal_forms_hook
from pulse.html.props import HTMLFormProps
from pulse.react_component import react_component
from pulse.vdom import Child

if TYPE_CHECKING:  # pragma: no cover
    from pulse.app import App
    from pulse.user_session import UserSession


__all__ = ["Form", "ManualForm", "FormData", "FormValue", "UploadFile", "FormRegistry"]
FormValue = str | UploadFile
FormData = dict[str, FormValue | list[FormValue]]


@react_component("PulseForm", "pulse-ui-client")
def client_form_component(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLFormProps],
): ...


@dataclass
class FormRegistration:
    id: str
    render_id: str
    route_path: str
    session_id: str
    on_submit: Callable[[FormData], Coroutine[Any, Any, None]]


class FormRegistry:
    def __init__(self, app: "App") -> None:
        self._app = app
        self._handlers: dict[str, FormRegistration] = {}
        self._forms_by_render: dict[str, set[str]] = {}

    def register(
        self,
        render_id: str,
        route_id: str,
        session_id: str,
        on_submit: Callable[[FormData], Coroutine[Any, Any, None]],
    ) -> FormRegistration:
        registration = FormRegistration(
            uuid.uuid4().hex,
            render_id=render_id,
            route_path=route_id,
            session_id=session_id,
            on_submit=on_submit,
        )
        self._handlers[registration.id] = registration
        self._forms_by_render.setdefault(registration.render_id, set()).add(
            registration.id
        )
        return registration

    def unregister(self, form_id: str) -> None:
        registration = self._handlers.pop(form_id, None)
        if registration is None:
            return
        bucket = self._forms_by_render.get(registration.render_id)
        if bucket is not None:
            bucket.discard(form_id)
            if len(bucket) == 0:
                self._forms_by_render.pop(registration.render_id)

    def remove_render(self, render_id: str) -> None:
        for form_id in list(self._forms_by_render.get(render_id, set())):
            self.unregister(form_id)

    async def handle_submit(
        self,
        form_id: str,
        request: Request,
        session: "UserSession",
    ) -> Response:
        registration = self._handlers.get(form_id)
        if registration is None:
            raise HTTPException(status_code=404, detail="Unknown form submission")

        if registration.session_id != session.sid:
            raise HTTPException(
                status_code=403, detail="Form does not belong to this session"
            )

        raw_form = await request.form()
        data = normalize_form_data(raw_form)

        # Deserialize complex data from __data__ field if present
        if "__data__" in data:
            data_value = data["__data__"]
            if isinstance(data_value, str):
                serialized_data = json.loads(data_value)
                deserialized_data = deserialize(serialized_data)
                # Merge deserialized data into form data, excluding __data__
                for key, value in deserialized_data.items():
                    if key != "__data__":
                        data[key] = value
                # Remove the __data__ field
                del data["__data__"]

        render = self._app.render_sessions.get(registration.render_id)
        if render is None:
            self.unregister(form_id)
            raise HTTPException(
                status_code=410, detail="Render session expired for form"
            )

        try:
            mount = render.get_route_mount(registration.route_path)
        except ValueError as exc:
            self.unregister(form_id)
            raise HTTPException(
                status_code=410,
                detail="Form route is no longer mounted",
            ) from exc

        with PulseContext.update(render=render, route=mount.route):
            await call_flexible(registration.on_submit, data)

        return Response(status_code=204)


def normalize_form_data(raw: StarletteFormData) -> FormData:
    normalized: FormData = {}
    for key, value in raw.multi_items():
        item: FormValue
        if isinstance(value, UploadFile):
            # Form submission tends to produce empty UploadFile objects for
            # empty file inputs
            if not value.filename and not value.size:
                continue
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


class PulseFormProps(HTMLFormProps, total=False):
    action: Never  # pyright: ignore[reportIncompatibleVariableOverride]
    method: Never  # pyright: ignore[reportIncompatibleVariableOverride]
    encType: Never  # pyright: ignore[reportIncompatibleVariableOverride]
    onSubmit: Never  # pyright: ignore[reportIncompatibleVariableOverride]


def Form(
    *children: Child,
    key: str,
    onSubmit: EventHandler1[FormData] | None = None,
    **props: Unpack[PulseFormProps],  # pyright: ignore[reportGeneralTypeIssues]
):
    if not isinstance(key, str) or not key:
        raise ValueError("ps.Form requires a non-empty string key")
    if not callable(onSubmit):
        raise ValueError("ps.Form requires an onSubmit callable")
    if "action" in props:
        raise ValueError("ps.Form does not allow overriding the form action")

    hook_state = HOOK_CONTEXT.get()
    if hook_state is None:
        raise RuntimeError("ps.Form can only be used within a component render")

    handler = stable(f"form:{key}", onSubmit)
    storage = internal_forms_hook()
    manual = storage.register(
        key,
        lambda: ManualForm(handler),
    )

    return manual(*children, key=key, **props)


class GeneratedFormProps(TypedDict):
    action: str
    method: str
    encType: str
    onSubmit: Callable[[], None]


class ManualForm:
    def __init__(self, on_submit: EventHandler1[FormData] | None = None) -> None:
        ctx = PulseContext.get()
        render = ctx.render
        route = ctx.route
        session = ctx.session
        if render is None:
            raise RuntimeError("ManualForm must be created during a render pass")
        if route is None:
            raise RuntimeError("ManualForm requires an active route context")
        if session is None:
            raise RuntimeError("ManualForm requires an active user session")

        self._submit_signal = Signal(False)
        self._app = ctx.app
        self._registration = self._app.forms.register(
            session_id=session.sid,
            render_id=render.id,
            route_id=route.pulse_route.unique_path(),
            on_submit=self.wrap_on_submit(on_submit),
        )

    def wrap_on_submit(self, on_submit: EventHandler1[FormData] | None):
        async def on_submit_handler(data: FormData):
            if on_submit:
                await maybe_await(call_flexible(on_submit, data))
            self._submit_signal.write(False)

        return on_submit_handler

    @property
    def is_submitting(self):
        return self._submit_signal.read()

    @property
    def registration(self):
        if self._registration is None:
            raise ValueError("This form has been disposed")
        return self._registration

    def _start_submit(self):
        self._submit_signal.write(True)

    def props(self) -> GeneratedFormProps:
        return {
            "action": f"{server_address()}/pulse/forms/{self.registration.id}",
            "method": "POST",
            "encType": "multipart/form-data",
            "onSubmit": self._start_submit,
        }

    def __call__(
        self,
        *children: Child,
        key: Optional[str] = None,
        **props: Unpack[PulseFormProps],
    ):
        props.update(self.props())  # pyright: ignore
        return client_form_component(*children, key=key, **props)

    def dispose(self) -> None:
        if self._registration is None:
            return
        self._app.forms.unregister(self._registration.id)
        self._registration = None

    def update(self, on_submit: EventHandler1[FormData] | None) -> None:
        self.registration.on_submit = self.wrap_on_submit(on_submit)
