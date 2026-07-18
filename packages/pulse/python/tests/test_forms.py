import json
from io import BytesIO
from typing import cast

import httpx
import pulse as ps
import pytest
from pulse import forms
from pulse.serializer import serialize
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

	assert forms._decode_structured_form_data(  # pyright: ignore[reportPrivateUsage]
		data, ps.Serializer()
	) == {
		"samples": [
			{
				"sample_id": "sample-1",
				"attachments": [first, second],
			}
		]
	}


def test_decode_structured_form_data_uses_configured_serializer():
	class RecordingSerializer:
		def __init__(self) -> None:
			self.payloads: list[object] = []

		def deserialize(self, payload: object) -> object:
			self.payloads.append(payload)
			return {"name": "Ada"}

	recording = RecordingSerializer()
	serializer = cast(ps.Serializer, cast(object, recording))
	data = forms.normalize_form_data(
		StarletteFormData(
			{
				"__pulse_data__": "[5,null]",
				"__pulse_files__": "[]",
			}
		)
	)

	assert forms._decode_structured_form_data(  # pyright: ignore[reportPrivateUsage]
		data, serializer
	) == {"name": "Ada"}
	assert recording.payloads == [[5, None]]


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
		forms._decode_structured_form_data(  # pyright: ignore[reportPrivateUsage]
			data, ps.Serializer()
		)


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
		forms._decode_structured_form_data(  # pyright: ignore[reportPrivateUsage]
			data, ps.Serializer()
		)


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
