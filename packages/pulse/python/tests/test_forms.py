import json
from io import BytesIO

import httpx
import pulse as ps
import pytest
from pulse import forms
from pulse.context import PulseContext
from pulse.routing import RouteContext
from pulse.serializer import serialize
from pulse.user_session import UserSession
from starlette.datastructures import FormData as StarletteFormData
from starlette.datastructures import UploadFile


def test_manual_form_action_is_origin_relative():
	@ps.component
	def home():
		return ps.div()

	route = ps.Route("a", home)
	app = ps.App(
		routes=[route],
		session_store=ps.CookieSessionStore(secret="test-secret"),
	)
	session = UserSession("session", {}, app)
	render = app.create_render("render", session)
	route_context = RouteContext(route.default_route_info(), route, render)

	with PulseContext(
		app=app,
		session=session,
		render=render,
		route=route_context,
	):
		manual = forms.ManualForm()
		action = manual.props()["action"]

	assert action == f"/_pulse/forms/render/{manual.registration.id}"
	manual.dispose()
	render.close()
	session.dispose()


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
	submitted = False

	@ps.component
	def home():
		return ps.div("ok")

	async def on_submit(_data: forms.FormData) -> None:
		nonlocal submitted
		submitted = True

	app = ps.App(routes=[ps.Route("a", home)])
	app.setup()
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
