import json
from io import BytesIO

import httpx
import pulse as ps
import pytest
from pulse import forms
from pulse.forms import internal_forms_hook
from pulse.hooks.core import HookContext
from pulse.reactive import Signal
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteContext, RouteInfo, RouteTree
from pulse.serializer import serialize
from pulse.user_session import UserSession
from starlette.datastructures import FormData as StarletteFormData
from starlette.datastructures import UploadFile


def test_normalize_form_data_groups_repeated_multipart_fields():
	first = UploadFile(BytesIO(b"first"), filename="first.txt")
	second = UploadFile(BytesIO(b"second"), filename="second.txt")
	raw = StarletteFormData(
		[
			("tag", "alpha"),
			("tag", "beta"),
			("attachments", first),
			("attachments", second),
		]
	)

	assert forms.normalize_form_data(raw) == {
		"tag": ["alpha", "beta"],
		"attachments": [first, second],
	}


def test_decode_structured_form_data_hydrates_manifest_files():
	first = UploadFile(BytesIO(b"first"), filename="first.txt")
	second = UploadFile(BytesIO(b"second"), filename="second.txt")
	manifest = [
		{
			"part": "__pulse_files__.0",
			"path": ["samples", 0, "attachments", 0],
		},
		{
			"part": "__pulse_files__.1",
			"path": ["samples", 0, "attachments", 1],
		},
	]
	data = forms.normalize_form_data(
		StarletteFormData(
			[
				(
					"__pulse_data__",
					json.dumps(
						serialize(
							{
								"samples": [
									{
										"sample_id": "sample-1",
										"attachments": [None, None],
									}
								]
							}
						)
					),
				),
				("__pulse_files__", json.dumps(manifest)),
				("__pulse_files__.0", first),
				("__pulse_files__.1", second),
			]
		)
	)

	assert forms._decode_structured_form_data(data) == {  # pyright: ignore[reportPrivateUsage]
		"samples": [
			{
				"sample_id": "sample-1",
				"attachments": [first, second],
			}
		]
	}


@pytest.mark.parametrize("reserved", ["__pulse_data__", "__pulse_files__"])
def test_decode_structured_form_data_rejects_reserved_values(reserved: str):
	data = forms.normalize_form_data(
		StarletteFormData(
			{
				"__pulse_data__": json.dumps(serialize({reserved: "user value"})),
				"__pulse_files__": "[]",
			}
		)
	)

	with pytest.raises(ValueError, match=f"Form field '{reserved}' is reserved"):
		forms._decode_structured_form_data(data)  # pyright: ignore[reportPrivateUsage]


def test_decode_structured_form_data_rejects_unreferenced_file_parts():
	file = UploadFile(BytesIO(b"content"), filename="file.txt")
	data = forms.normalize_form_data(
		StarletteFormData(
			{
				"__pulse_data__": json.dumps(serialize({"name": "Ada"})),
				"__pulse_files__": "[]",
				"__pulse_files__.0": file,
			}
		)
	)

	with pytest.raises(ValueError, match="unreferenced file parts"):
		forms._decode_structured_form_data(data)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"data_value",
	[
		"not-json",
		"[[[0],[],[],[]],1e1000000]",
		'[[[],[],[],[]],{"amount":NaN}]',
	],
)
async def test_invalid_structured_form_payload_returns_400(
	monkeypatch: pytest.MonkeyPatch,
	data_value: str,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	submitted = False

	@ps.component
	def home():
		return ps.div("ok")

	async def on_submit(_data: forms.FormData) -> None:
		nonlocal submitted
		submitted = True

	app = ps.App(routes=[ps.Route("a", home)])
	app.setup("http://example.com")
	try:
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport,
			base_url="http://testserver",
		) as client:
			prerender = await client.post(
				"/_pulse/prerender",
				json={
					"paths": ["/a"],
					"routeInfo": {
						"pathname": "/a",
						"hash": "",
						"query": "",
						"queryParams": {},
						"pathParams": {},
						"catchall": [],
					},
				},
			)
			assert prerender.status_code == 200

			render = next(iter(app.render_sessions.values()))
			session = next(iter(app.user_sessions.values()))
			registration = render.forms.register(
				render_id=render.id,
				route_id="/a",
				session_id=session.sid,
				on_submit=on_submit,
			)
			response = await client.post(
				f"/_pulse/forms/{render.id}/{registration.id}",
				files={
					"__pulse_data__": (None, data_value),
					"__pulse_files__": (None, "[]"),
				},
			)

		assert response.status_code == 400
		assert response.json() == {"detail": "Invalid Pulse form payload"}
		assert not submitted
	finally:
		await app.close()


def make_form_context():
	@ps.component
	def Page():
		return ps.div()

	route = Route("/", Page)
	render = RenderSession(
		"test", RouteTree([route]), server_address="http://testserver"
	)
	app = ps.App(routes=[route])
	route_info: RouteInfo = {
		"pathname": "/",
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}
	route_ctx = RouteContext(route_info, route, render)
	session = UserSession("test-session", {}, app)
	return app, render, session, route_ctx


async def noop_submit(_data: forms.FormData) -> None:
	return None


def test_form_survives_failed_render():
	"""A render that raises before ps.Form must keep the form registered."""
	app, render, session, route_ctx = make_form_context()
	ctx = HookContext()
	fail = Signal(False)
	instances: list[forms.ManualForm] = []

	@ps.component
	def Comp():
		if fail():
			raise RuntimeError("transient")
		node = ps.Form(key="f", onSubmit=noop_submit)
		instances.append(internal_forms_hook().forms["f"])
		return node

	with ps.PulseContext(app=app, session=session, render=render, route=route_ctx):
		with ctx:
			Comp.fn()  # type: ignore[attr-defined]
		first = instances[0]
		registration_id = first.registration.id

		fail.write(True)
		with pytest.raises(RuntimeError, match="transient"), ctx:
			Comp.fn()  # type: ignore[attr-defined]

		# Client still displays the form, so its handler must stay registered.
		assert registration_id in render.forms._handlers  # pyright: ignore[reportPrivateUsage]

		fail.write(False)
		with ctx:
			Comp.fn()  # type: ignore[attr-defined]

		assert instances[1] is first
		assert first.registration.id == registration_id

	session.dispose()


def test_form_disposed_by_first_successful_render_after_failure():
	"""A form genuinely dropped by the next successful render is still disposed."""
	app, render, session, route_ctx = make_form_context()
	ctx = HookContext()
	fail = Signal(False)
	show = Signal(True)
	instances: list[forms.ManualForm] = []

	@ps.component
	def Comp():
		if fail():
			raise RuntimeError("transient")
		if not show():
			return ps.div()
		node = ps.Form(key="f", onSubmit=noop_submit)
		instances.append(internal_forms_hook().forms["f"])
		return node

	with ps.PulseContext(app=app, session=session, render=render, route=route_ctx):
		with ctx:
			Comp.fn()  # type: ignore[attr-defined]
		registration_id = instances[0].registration.id

		fail.write(True)
		with pytest.raises(RuntimeError, match="transient"), ctx:
			Comp.fn()  # type: ignore[attr-defined]

		fail.write(False)
		show.write(False)
		with ctx:
			Comp.fn()  # type: ignore[attr-defined]

		assert registration_id not in render.forms._handlers  # pyright: ignore[reportPrivateUsage]
		with pytest.raises(ValueError, match="disposed"):
			_ = instances[0].registration

	session.dispose()
