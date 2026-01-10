"""
Tests for SSR endpoint that handles HTTP requests.

The SSR endpoint:
1. Takes HTTP GET request with path
2. Matches route
3. Prerenders VDOM
4. POSTs to Bun render server
5. Returns HTML response
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pulse as ps
import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient
from pulse.app import App
from pulse.env import env
from pulse.routing import Route


@pytest.fixture
def simple_app(monkeypatch: MonkeyPatch) -> App:
	"""Create a simple Pulse app for testing."""
	# Set required env vars for single-server mode
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:5173")

	app = App(
		routes=[
			Route("/", ps.component(lambda: ps.div()["Hello"])),
			Route("/users/:id", ps.component(lambda: ps.div()["User"])),
		],
		mode="single-server",
	)
	app.setup("http://localhost:8000")
	return app


@pytest.fixture
def client(simple_app: App) -> TestClient:
	"""Create a FastAPI test client."""
	return TestClient(simple_app.asgi)


def test_ssr_endpoint_requires_bun_render_server(client: TestClient) -> None:
	"""Test SSR endpoint fails if Bun render server not configured."""
	# Bun render server address not set
	assert env.bun_render_server_address is None

	response = client.get("/")
	assert response.status_code == 500
	assert "Bun render server not configured" in response.text


def test_ssr_endpoint_renders_route(
	client: TestClient, monkeypatch: MonkeyPatch
) -> None:
	"""Test SSR endpoint renders a route."""
	# Set Bun render server address
	monkeypatch.setenv("PULSE_BUN_RENDER_SERVER_ADDRESS", "http://localhost:3001")

	# Mock httpx.AsyncClient.post to simulate Bun render server
	with patch("pulse.app.httpx.AsyncClient") as mock_client_class:
		mock_client = AsyncMock()
		mock_client_class.return_value.__aenter__.return_value = mock_client

		# Mock the response from Bun render server
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.text = "<html><body>Hello</body></html>"
		mock_client.post.return_value = mock_response

		response = client.get("/")

		# Verify response
		assert response.status_code == 200
		# Verify HTML is wrapped in full document shell
		assert "<!DOCTYPE html>" in response.text
		assert '<html lang="en">' in response.text
		assert "__PULSE_DATA__" in response.text
		assert "Hello" in response.text
		assert response.headers["content-type"] == "text/html; charset=utf-8"

		# Verify POST to Bun server
		mock_client.post.assert_called_once()
		call_args = mock_client.post.call_args
		assert call_args[0][0] == "http://localhost:3001/render"
		assert "vdom" in call_args[1]["json"]
		assert "routeInfo" in call_args[1]["json"]


def test_ssr_endpoint_passes_route_info(
	client: TestClient, monkeypatch: MonkeyPatch
) -> None:
	"""Test SSR endpoint passes correct route info to Bun server."""
	monkeypatch.setenv("PULSE_BUN_RENDER_SERVER_ADDRESS", "http://localhost:3001")

	with patch("pulse.app.httpx.AsyncClient") as mock_client_class:
		mock_client = AsyncMock()
		mock_client_class.return_value.__aenter__.return_value = mock_client

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.text = "<html></html>"
		mock_client.post.return_value = mock_response

		_ = client.get("/?test=value")

		# Verify POST args include correct route info
		call_args = mock_client.post.call_args
		request_data = call_args[1]["json"]
		route_info = request_data["routeInfo"]

		assert route_info["location"]["pathname"] == "/"
		assert route_info["location"]["search"] == "test=value"
		assert route_info["params"] == {}


def test_ssr_endpoint_handles_bun_server_error(
	client: TestClient, monkeypatch: MonkeyPatch
) -> None:
	"""Test SSR endpoint handles Bun render server errors."""
	monkeypatch.setenv("PULSE_BUN_RENDER_SERVER_ADDRESS", "http://localhost:3001")

	with patch("pulse.app.httpx.AsyncClient") as mock_client_class:
		mock_client = AsyncMock()
		mock_client_class.return_value.__aenter__.return_value = mock_client

		mock_response = MagicMock()
		mock_response.status_code = 500
		mock_response.text = "Render error"
		mock_client.post.return_value = mock_response

		response = client.get("/")

		assert response.status_code == 500
		assert "Bun render server error" in response.text


def test_ssr_endpoint_handles_connection_error(
	client: TestClient, monkeypatch: MonkeyPatch
) -> None:
	"""Test SSR endpoint handles connection errors to Bun server."""
	monkeypatch.setenv("PULSE_BUN_RENDER_SERVER_ADDRESS", "http://localhost:3001")

	with patch("pulse.app.httpx.AsyncClient") as mock_client_class:
		import httpx

		mock_client = AsyncMock()
		mock_client_class.return_value.__aenter__.return_value = mock_client

		# Simulate connection error
		mock_client.post.side_effect = httpx.RequestError("Connection refused")

		response = client.get("/")

		assert response.status_code == 503
		assert "Failed to connect to Bun render server" in response.text
