from __future__ import annotations

import json
import os

from fastapi import FastAPI, WebSocket

DEPLOYMENT_ID = os.getenv("POC_DEPLOYMENT_ID", "local")

app = FastAPI()


@app.get("/")
async def root() -> dict[str, str]:
	return {"deployment": DEPLOYMENT_ID}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
	await websocket.accept()
	while True:
		message = await websocket.receive_text()
		await websocket.send_text(
			json.dumps(
				{
					"deployment": DEPLOYMENT_ID,
					"message": message,
				}
			)
		)
