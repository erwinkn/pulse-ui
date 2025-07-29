"""
FastAPI server with WebSocket support for Pulse UI.

This module provides the main server that handles both HTTP and WebSocket connections
for the Pulse UI system, including automatic route generation and callback handling.
"""

import asyncio
import json
import logging
import socket
from typing import Dict, Any, Set, Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .nodes import execute_callback, get_all_callbacks
from .codegen import generate_all_routes

logger = logging.getLogger(__name__)


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"Could not find available port after {max_attempts} attempts starting from {start_port}"
    )


class PulseServer:
    """FastAPI server with WebSocket support for Pulse UI."""

    def __init__(self, host: str = "localhost", port: int = 8000, app_routes: Optional[List] = None):
        self.app = FastAPI(title="Pulse UI Server")
        self.host = host
        self.port = port
        self.app_routes = app_routes
        self.connected_clients: Set[WebSocket] = set()

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup routes
        self.setup_routes()

    def setup_routes(self):
        """Setup HTTP and WebSocket routes."""

        @self.app.get("/")
        async def health_check():
            return {"status": "ok", "message": "Pulse UI Server is running"}

        @self.app.get("/callbacks")
        async def list_callbacks():
            return {"callbacks": list(get_all_callbacks().keys())}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connections."""
        await websocket.accept()
        self.connected_clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")

        try:
            while True:
                data = await websocket.receive_text()
                await self.process_message(websocket, data)
        except WebSocketDisconnect:
            self.connected_clients.discard(websocket)
            logger.info(
                f"Client disconnected. Total clients: {len(self.connected_clients)}"
            )
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self.connected_clients.discard(websocket)

    async def process_message(self, websocket: WebSocket, message: str):
        """Process incoming WebSocket messages."""
        logger.info(f"📥 Received WebSocket message: {message}")
        try:
            data = json.loads(message)
            message_type = data.get("type")
            request_id = data.get("request_id")
            logger.info(
                f"📋 Parsed message type: {message_type}, request_id: {request_id}"
            )

            if message_type == "callback_invoke":
                callback_key = data.get("callback_key")
                if callback_key:
                    logger.info(f"Executing callback: {callback_key}")
                    success = execute_callback(callback_key)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "callback_response",
                                "request_id": request_id,
                                "success": success,
                                "callback_key": callback_key,
                            }
                        )
                    )
                else:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "request_id": request_id,
                                "message": "Missing callback_key",
                            }
                        )
                    )
            elif message_type == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong", "request_id": request_id})
                )
            elif message_type == "get_callbacks":
                callbacks_list = list(get_all_callbacks().keys())
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "callbacks_list",
                            "request_id": request_id,
                            "callbacks": callbacks_list,
                        }
                    )
                )
            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "message": f"Unknown message type: {message_type}",
                        }
                    )
                )
        except json.JSONDecodeError:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Invalid JSON format"})
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "request_id": request_id, "message": str(e)}
                )
            )

    def generate_routes(self):
        """Generate TypeScript files from Python routes."""
        logger.info("Generating TypeScript routes...")
        generate_all_routes(
            host=self.host, port=self.port, clear_existing_callbacks=True, app_routes=self.app_routes
        )

    def run(self, auto_generate: bool = True):
        """Start the FastAPI server."""
        if auto_generate:
            self.generate_routes()

        logger.info(f"🚀 Starting Pulse UI Server on http://{self.host}:{self.port}")
        logger.info(f"🔌 WebSocket endpoint: ws://{self.host}:{self.port}/ws")

        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")


def start_server(
    host: str = "localhost",
    port: int = 8000,
    auto_generate: bool = True,
    find_port: bool = True,
    app_routes: Optional[List] = None,
):
    """Start the Pulse UI FastAPI server."""
    if find_port:
        try:
            available_port = find_available_port(port)
            if available_port != port:
                logger.info(f"Port {port} not available, using port {available_port}")
            port = available_port
        except RuntimeError as e:
            logger.error(f"Failed to find available port: {e}")
            raise

    server = PulseServer(host, port, app_routes=app_routes)
    server.run(auto_generate=auto_generate)
