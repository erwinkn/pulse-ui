import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
	TYPE_CHECKING,
	Never,
	TypedDict,
	Unpack,
	override,
)

from fastapi import HTTPException, Request, Response
from starlette.datastructures import FormData as StarletteFormData
from starlette.datastructures import UploadFile

from pulse.context import PulseContext
from pulse.dom.props import HTMLFormProps
from pulse.helpers import Disposable, call_flexible, maybe_await
from pulse.hooks.core import HOOK_CONTEXT, HookMetadata, HookState, hooks
from pulse.hooks.runtime import server_address
from pulse.hooks.stable import stable
from pulse.react_component import react_component
from pulse.reactive import Signal
from pulse.serializer import deserialize
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Node
from pulse.types.event_handler import EventHandler1

if TYPE_CHECKING:
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession


__all__ = [
	"Form",
	"ManualForm",
	"FormData",
	"FormValue",
	"UploadFile",
	"FormRegistry",
	"FormStorage",
	"internal_forms_hook",
]

FormValue = str | UploadFile
"""Individual form field value: ``str | UploadFile``."""

FormData = dict[str, FormValue | list[FormValue]]
"""Parsed form submission data.

Values are either single or multiple (for repeated field names).
Type alias for ``dict[str, FormValue | list[FormValue]]``.
"""


@react_component(Import("PulseForm", "pulse-ui-client"))
def client_form_component(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLFormProps],
): ...


@dataclass
class FormRegistration:
	"""Internal registration info for a form.

	Attributes:
		id: Unique form identifier.
		render_id: Associated render session ID.
		route_path: Route path this form is bound to.
		session_id: Associated user session ID.
		on_submit: Async callback for form submission.
	"""

	id: str
	render_id: str
	route_path: str
	session_id: str
	on_submit: Callable[[FormData], Awaitable[None]]


class FormRegistry(Disposable):
	"""Internal class managing form registrations.

	Not typically used directly. Forms are registered automatically via
	``ps.Form`` or ``ManualForm``.
	"""

	def __init__(self, render: "RenderSession") -> None:
		self._render: "RenderSession" = render
		self._handlers: dict[str, FormRegistration] = {}

	def register(
		self,
		render_id: str,
		route_id: str,
		session_id: str,
		on_submit: Callable[[FormData], Awaitable[None]],
	) -> FormRegistration:
		"""Register a form handler.

		Args:
			render_id: Render session ID.
			route_id: Route path.
			session_id: User session ID.
			on_submit: Async callback for form submission.

		Returns:
			FormRegistration with generated form ID.
		"""
		registration = FormRegistration(
			uuid.uuid4().hex,
			render_id=render_id,
			route_path=route_id,
			session_id=session_id,
			on_submit=on_submit,
		)
		self._handlers[registration.id] = registration
		return registration

	def unregister(self, form_id: str) -> None:
		"""Unregister a form handler.

		Args:
			form_id: The form ID to unregister.
		"""
		self._handlers.pop(form_id, None)

	@override
	def dispose(self) -> None:
		"""Clean up all registered forms."""
		self._handlers.clear()

	async def handle_submit(
		self,
		form_id: str,
		request: Request,
		session: "UserSession",
	) -> Response:
		"""Handle incoming form submission.

		Args:
			form_id: The form ID being submitted.
			request: The HTTP request.
			session: The user session.

		Returns:
			HTTP response (204 on success).

		Raises:
			HTTPException: If form not found (404), session mismatch (403),
				or route unmounted (410).
		"""
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

		try:
			mount = self._render.get_route_mount(registration.route_path)
		except ValueError as exc:
			self.unregister(form_id)
			raise HTTPException(
				status_code=410,
				detail="Form route is no longer mounted",
			) from exc

		with PulseContext.update(render=self._render, route=mount.route):
			await call_flexible(registration.on_submit, data)

		return Response(status_code=204)


def normalize_form_data(raw: StarletteFormData) -> FormData:
	"""Convert Starlette FormData to normalized FormData dict.

	Handles multiple values for the same key and filters out empty file uploads.

	Args:
		raw: Starlette FormData from request.form().

	Returns:
		Normalized FormData dictionary.
	"""
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
	"""Form props that exclude action, method, encType, and onSubmit.

	These props are auto-generated by Pulse for form handling.
	"""

	action: Never  # pyright: ignore[reportIncompatibleVariableOverride]
	method: Never  # pyright: ignore[reportIncompatibleVariableOverride]
	encType: Never  # pyright: ignore[reportIncompatibleVariableOverride]
	onSubmit: Never  # pyright: ignore[reportIncompatibleVariableOverride]


def Form(
	*children: Node,
	key: str,
	onSubmit: EventHandler1[FormData] | None = None,
	**props: Unpack[PulseFormProps],  # pyright: ignore[reportGeneralTypeIssues]
):
	"""Server-registered HTML form component.

	Automatically wires up form submission to a Python handler. Uses
	``multipart/form-data`` encoding to support file uploads.

	Args:
		*children: Form content (inputs, buttons, etc.).
		key: Unique form identifier (required, non-empty string).
		onSubmit: Submit handler receiving parsed FormData.
		**props: Standard HTML form props (except action, method, encType, onSubmit).

	Returns:
		Form node.

	Raises:
		ValueError: If key is empty or onSubmit is not callable.
		RuntimeError: If called outside a component render.

	Example:

	```python
	async def handle_submit(data: ps.FormData):
	    name = data.get("name")  # str
	    file = data.get("avatar")  # UploadFile
	    await save_user(name, file)

	def my_form():
	    return ps.Form(
	        m.TextInput(name="name", label="Name"),
	        m.FileInput(name="avatar", label="Avatar"),
	        m.Button("Submit", type="submit"),
	        key="user-form",
	        onSubmit=handle_submit,
	    )
	```

	Note:
		- ``key`` must be unique within the render.
		- Cannot override ``action``, ``method``, ``encType``, or ``onSubmit`` via props.
		- Handler receives parsed form data as a ``FormData`` dict.
	"""
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
	"""Form props generated by ``ManualForm.props()``.

	Attributes:
		action: Form submission URL.
		method: HTTP method ("POST").
		encType: Encoding type ("multipart/form-data").
		onSubmit: Submission trigger callback.
	"""

	action: str
	method: str
	encType: str
	onSubmit: Callable[[], None]


class ManualForm(Disposable):
	"""Low-level form handler for custom form implementations.

	Use when you need more control over form rendering than ``ps.Form`` provides.

	Attributes:
		is_submitting: Whether the form is currently submitting.
		registration: Form registration info (raises if disposed).

	Example:

	```python
	def custom_form():
	    manual = ManualForm(on_submit=handle_data)

	    # Option 1: Render directly
	    return manual(
	        m.TextInput(name="field"),
	        m.Button("Submit", type="submit"),
	        key="my-form",
	    )

	    # Option 2: Use props manually
	    form_props = manual.props()
	    return m.form(
	        m.TextInput(name="field"),
	        m.Button("Submit", type="submit"),
	        **form_props,
	    )
	```
	"""

	_submit_signal: Signal[bool]
	_render: "RenderSession"
	_registration: FormRegistration | None

	def __init__(self, on_submit: EventHandler1[FormData] | None = None) -> None:
		"""Initialize a manual form handler.

		Args:
			on_submit: Optional submit handler receiving parsed FormData.

		Raises:
			RuntimeError: If called outside a render pass, route context,
				or user session.
		"""
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
		self._render = render
		self._registration = render.forms.register(
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
	def is_submitting(self) -> bool:
		"""Whether the form is currently submitting."""
		return self._submit_signal.read()

	@property
	def registration(self) -> FormRegistration:
		"""Form registration info.

		Raises:
			ValueError: If the form has been disposed.
		"""
		if self._registration is None:
			raise ValueError("This form has been disposed")
		return self._registration

	def _start_submit(self) -> None:
		self._submit_signal.write(True)

	def props(self) -> GeneratedFormProps:
		"""Get form props for manual binding to a form element.

		Returns:
			Dict with action, method, encType, and onSubmit props.
		"""
		return {
			"action": f"{server_address()}/pulse/forms/{self._render.id}/{self.registration.id}",
			"method": "POST",
			"encType": "multipart/form-data",
			"onSubmit": self._start_submit,
		}

	def __call__(
		self,
		*children: Node,
		key: str | None = None,
		**props: Unpack[PulseFormProps],
	):
		"""Render as a form element with children.

		Args:
			*children: Form content.
			key: Optional element key.
			**props: Additional form props.

		Returns:
			Form node with auto-generated submission props.
		"""
		props.update(self.props())  # pyright: ignore[reportCallIssue, reportArgumentType]
		return client_form_component(*children, key=key, **props)

	@override
	def dispose(self) -> None:
		"""Unregister the form and clean up."""
		if self._registration is None:
			return
		self._render.forms.unregister(self._registration.id)
		self._registration = None

	def update(self, on_submit: EventHandler1[FormData] | None) -> None:
		"""Update the submit handler.

		Args:
			on_submit: New submit handler.
		"""
		self.registration.on_submit = self.wrap_on_submit(on_submit)


class FormStorage(HookState):
	"""Internal hook state for managing form lifecycle within renders.

	Not typically used directly. Manages form persistence and cleanup across
	render cycles.
	"""

	__slots__ = ("forms", "prev_forms", "render_mark")  # pyright: ignore[reportUnannotatedClassAttribute]
	render_mark: int

	def __init__(self) -> None:
		super().__init__()
		self.forms: dict[str, ManualForm] = {}
		self.prev_forms: dict[str, ManualForm] = {}
		self.render_mark = 0

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		if self.render_mark == render_cycle:
			return
		self.prev_forms = self.forms
		self.forms = {}
		self.render_mark = render_cycle

	@override
	def on_render_end(self, render_cycle: int) -> None:
		if not self.prev_forms:
			return
		for form in self.prev_forms.values():
			form.dispose()
		self.prev_forms.clear()

	def register(
		self,
		key: str,
		factory: Callable[[], ManualForm],
	) -> ManualForm:
		if key in self.forms:
			raise RuntimeError(
				f"Duplicate ps.Form id '{key}' detected within the same render"
			)
		form = self.prev_forms.pop(key, None)
		if form is None:
			form = factory()
		self.forms[key] = form
		return form

	@override
	def dispose(self) -> None:
		for form in self.forms.values():
			form.dispose()
		for form in self.prev_forms.values():
			form.dispose()
		self.forms.clear()
		self.prev_forms.clear()


def _forms_factory():
	return FormStorage()


internal_forms_hook = hooks.create(
	"pulse:core.forms",
	_forms_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for ps.Form manual forms",
	),
)
