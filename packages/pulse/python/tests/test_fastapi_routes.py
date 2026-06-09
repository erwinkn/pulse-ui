from typing import Any

import httpx
import pulse as ps
import pytest
from fastapi import APIRouter, Response


@pytest.mark.asyncio
async def test_fastapi_routes_unwrap_reactive_response_values():
	app = ps.App(routes=[])

	@app.fastapi.get("/reactive")
	def reactive_payload() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
		count = ps.Signal(2)
		doubled = ps.Computed(lambda: count() * 2)
		return {
			"count": count,
			"nested": {"doubled": doubled},
			"items": ps.reactive([count, {"status": ps.Signal("ok")}]),
		}

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/reactive")

	assert response.status_code == 200
	assert response.json() == {
		"count": 2,
		"nested": {"doubled": 4},
		"items": [2, {"status": "ok"}],
	}


@pytest.mark.asyncio
async def test_included_fastapi_routers_unwrap_reactive_response_values():
	app = ps.App(routes=[])
	router = APIRouter()

	@router.get("/reactive")
	def reactive_payload() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
		return {"count": ps.Signal(3)}

	app.fastapi.include_router(router, prefix="/api")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/api/reactive")

	assert response.status_code == 200
	assert response.json() == {"count": 3}


@pytest.mark.asyncio
async def test_fastapi_routes_leave_response_instances_unchanged():
	app = ps.App(routes=[])

	@app.fastapi.get("/raw")
	def raw_response():  # pyright: ignore[reportUnusedFunction]
		return Response("raw", media_type="text/plain")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/raw")

	assert response.status_code == 200
	assert response.text == "raw"
	assert response.headers["content-type"].startswith("text/plain")
