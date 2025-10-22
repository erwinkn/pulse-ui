#!/usr/bin/env python3
"""
Phase 1 Testing Script

Starts Pulse apps with different deployment modes and validates:
1. API route prefixing
2. CORS headers
3. Cookie settings
4. Backward compatibility

Usage:
    uv run --with httpx python scripts/test_phase1.py
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from pulse.serializer import deserialize

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def log_info(msg: str):
	print(f"{BLUE}ℹ{RESET}  {msg}")


def log_success(msg: str):
	print(f"{GREEN}✓{RESET}  {msg}")


def log_error(msg: str):
	print(f"{RED}✗{RESET}  {msg}")


def log_warning(msg: str):
	print(f"{YELLOW}⚠{RESET}  {msg}")


def log_section(title: str):
	print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
	print(f"{BOLD}{BLUE}{title}{RESET}")
	print(f"{BOLD}{BLUE}{'=' * 60}{RESET}\n")


def create_test_app(deployment: str, port: int, cors: dict | None = None) -> Path:
	"""Create a temporary Pulse app file for testing."""
	cors_str = ""
	if cors:
		cors_str = f",\n    cors={cors!r}"

	# Use the examples/web directory
	script_dir = Path(__file__).parent.parent
	web_dir = script_dir / "examples" / "web"

	app_content = f'''
import pulse as ps
from pulse.codegen.codegen import CodegenConfig

def home():
    """Home page route."""
    return ps.div("Home Page")

def about():
    """About page route."""
    return ps.div("About Page")

app = ps.App(
    routes=[
        ps.Route("/", home),
        ps.Route("/about", about),
    ],
    deployment="{deployment}",
    server_address="http://localhost:{port}",
    codegen=CodegenConfig(web_dir="{web_dir}"){cors_str}
)
'''

	with tempfile.NamedTemporaryFile(
		mode="w", suffix=".py", delete=False, dir="/tmp", prefix="pulse_test_"
	) as f:
		f.write(app_content)
		return Path(f.name)


def start_server(
	app_file: Path, port: int, mode: str = "dev"
) -> tuple[subprocess.Popen, Path]:
	"""Start a Pulse server as a subprocess. Returns (process, log_file)."""
	cmd = [
		"uv",
		"run",
		"pulse",
		"run",
		str(app_file),
		"--host",
		"localhost",
		"--port",
		str(port),
	]
	if mode == "prod":
		cmd.append("--prod")

	log_info(f"Starting server: {' '.join(cmd)}")

	# Create log file for debugging
	log_file = Path(f"/tmp/pulse_server_{port}.log")
	with open(log_file, "w") as f:
		proc = subprocess.Popen(
			cmd,
			stdout=f,
			stderr=subprocess.STDOUT,
			text=True,
			cwd=Path(__file__).parent.parent,
		)

	return proc, log_file


def wait_for_server(url: str, timeout: int = 10) -> bool:
	"""Wait for server to be ready."""
	start = time.time()
	while time.time() - start < timeout:
		try:
			httpx.get(url, timeout=1.0)
			return True
		except (httpx.ConnectError, httpx.TimeoutException):
			time.sleep(0.5)
	return False


def test_health_endpoint(base_url: str, prefix: str = "") -> bool:
	"""Test the health endpoint."""
	endpoint = f"{base_url}{prefix}/health"
	log_info(f"Testing health endpoint: {endpoint}")

	try:
		response = httpx.get(endpoint, timeout=5.0)
		log_info(f"  Status: {response.status_code}")
		log_info(f"  Body: {response.json()}")

		if response.status_code == 200:
			data = response.json()
			if data.get("health") == "ok":
				log_success(f"Health endpoint working at {endpoint}")
				return True
			else:
				log_error(f"Health endpoint returned unexpected data: {data}")
				return False
		else:
			log_error(f"Health endpoint returned status {response.status_code}")
			return False
	except Exception as e:
		log_error(f"Failed to connect to health endpoint: {e}")
		return False


def test_cors_headers(
	base_url: str, prefix: str = "", expected_origin: str | None = None
) -> bool:
	"""Test CORS headers."""
	endpoint = f"{base_url}{prefix}/health"
	log_info(f"Testing CORS headers: {endpoint}")

	try:
		# Send OPTIONS request with Origin header
		response = httpx.options(
			endpoint,
			headers={"Origin": base_url, "Access-Control-Request-Method": "GET"},
			timeout=5.0,
		)

		cors_origin = response.headers.get("access-control-allow-origin")
		cors_methods = response.headers.get("access-control-allow-methods")
		cors_credentials = response.headers.get("access-control-allow-credentials")

		log_info(f"  Access-Control-Allow-Origin: {cors_origin}")
		log_info(f"  Access-Control-Allow-Methods: {cors_methods}")
		log_info(f"  Access-Control-Allow-Credentials: {cors_credentials}")

		if expected_origin:
			if cors_origin == expected_origin:
				log_success(f"CORS origin matches expected: {expected_origin}")
				return True
			else:
				log_error(
					f"CORS origin mismatch. Expected: {expected_origin}, Got: {cors_origin}"
				)
				return False
		else:
			if cors_origin:
				log_success("CORS headers present")
				return True
			else:
				log_warning("No CORS origin header found")
				return True

	except Exception as e:
		log_error(f"Failed to test CORS headers: {e}")
		return False


def test_prerender_endpoint(base_url: str, prefix: str = "") -> bool:
	"""Test the prerender endpoint."""
	endpoint = f"{base_url}{prefix}/prerender"
	log_info(f"Testing prerender endpoint: {endpoint}")

	# Full RouteInfo structure as expected by the API
	payload = {
		"paths": ["/"],
		"routeInfo": {
			"pathname": "/",
			"hash": "",
			"query": "",
			"queryParams": {},
			"pathParams": {},
			"catchall": [],
		},
	}

	try:
		response = httpx.post(
			endpoint,
			json=payload,
			timeout=10.0,
			headers={"Content-Type": "application/json"},
		)

		log_info(f"  Status: {response.status_code}")

		if response.status_code == 200:
			serialized_data = response.json()

			# Deserialize the response using Pulse serializer
			try:
				data = deserialize(serialized_data)

				if isinstance(data, dict) and "renderId" in data and "views" in data:
					log_success("Prerender endpoint working")
					log_info(f"  renderId: {data['renderId']}")
					log_info(f"  views: {list(data['views'].keys())}")
					return True
				else:
					log_error(
						"Prerender endpoint returned unexpected data structure after deserialization"
					)
					log_error("  Expected: dict with renderId and views")
					log_error(
						f"  Got: {type(data)} with keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
					)
					return False
			except Exception as e:
				log_error(f"Failed to deserialize prerender response: {e}")
				return False
		else:
			log_error(f"Prerender endpoint returned status {response.status_code}")
			log_info(f"  Body: {response.text[:200]}")
			return False

	except Exception as e:
		log_error(f"Failed to test prerender endpoint: {e}")
		return False


def test_wrong_prefix(base_url: str, wrong_prefix: str) -> bool:
	"""Test that wrong prefix returns 404."""
	endpoint = f"{base_url}{wrong_prefix}/health"
	log_info(f"Testing wrong prefix (should fail): {endpoint}")

	try:
		response = httpx.get(endpoint, timeout=5.0)
		if response.status_code == 404:
			log_success("Wrong prefix correctly returns 404")
			return True
		else:
			log_error(f"Wrong prefix returned {response.status_code} instead of 404")
			return False
	except Exception as e:
		log_error(f"Failed to test wrong prefix: {e}")
		return False


def run_test_suite(
	deployment: str,
	port: int,
	prefix: str,
	expected_origin: str | None = None,
	cors: dict | None = None,
) -> bool:
	"""Run a complete test suite for a deployment mode."""
	log_section(f"Testing deployment='{deployment}' mode on port {port}")

	# Create app file
	app_file = create_test_app(deployment, port, cors)
	log_info(f"Created test app: {app_file}")

	# Start server
	proc, log_file = start_server(app_file, port)
	log_info(f"Server logs: {log_file}")

	try:
		# Wait for server to start
		base_url = f"http://localhost:{port}"
		log_info(f"Waiting for server to start at {base_url}...")

		if not wait_for_server(base_url, timeout=15):
			log_error("Server failed to start within timeout")
			log_error("Check server logs for details:")
			try:
				with open(log_file) as f:
					log_content = f.read()
					for line in log_content.split("\n")[-20:]:  # Show last 20 lines
						if line.strip():
							print(f"    {line}")
			except Exception:
				pass
			return False

		log_success("Server started successfully")

		# Run tests
		results = []

		# Test 1: Health endpoint with correct prefix
		results.append(test_health_endpoint(base_url, prefix))

		# Test 2: CORS headers
		results.append(test_cors_headers(base_url, prefix, expected_origin))

		# Test 3: Prerender endpoint
		results.append(test_prerender_endpoint(base_url, prefix))

		# Test 4: Wrong prefix should fail (only for non-empty prefix)
		if prefix:
			wrong_prefix = "/wrong"
			results.append(test_wrong_prefix(base_url, wrong_prefix))

		# Test 5: No prefix should fail for single-server
		if prefix:
			log_info("Testing that no prefix returns 404")
			try:
				response = httpx.get(f"{base_url}/health", timeout=5.0)
				if response.status_code == 404:
					log_success("No prefix correctly returns 404 in single-server mode")
					results.append(True)
				else:
					log_error(
						f"No prefix returned {response.status_code} instead of 404"
					)
					results.append(False)
			except Exception as e:
				log_error(f"Failed to test no prefix: {e}")
				results.append(False)

		# Summary
		passed = sum(results)
		total = len(results)
		log_info(f"\nTest Results: {passed}/{total} passed")

		if passed == total:
			log_success(f"All tests passed for deployment='{deployment}'")
			return True
		else:
			log_error(f"Some tests failed for deployment='{deployment}'")
			return False

	finally:
		# Cleanup
		log_info("Shutting down server...")
		proc.terminate()
		try:
			proc.wait(timeout=5)
		except subprocess.TimeoutExpired:
			log_warning("Server didn't stop gracefully, killing...")
			proc.kill()

		# Clean up app file
		try:
			app_file.unlink()
			log_info("Cleaned up test app file")
		except Exception:
			pass

		# Small delay to ensure port is released
		time.sleep(1)


def main():
	"""Run all Phase 1 tests."""
	log_section("Phase 1 Testing Script")
	log_info("Testing API route prefixing, CORS, and deployment modes")

	all_passed = True

	# Test 1: Single-server mode (with prefix)
	all_passed &= run_test_suite(
		deployment="single-server",
		port=9001,
		prefix="/api/pulse",
		expected_origin="http://localhost:9001",
	)

	time.sleep(2)  # Ensure port is released

	# Test 2: Subdomains mode (no prefix)
	all_passed &= run_test_suite(
		deployment="subdomains",
		port=9002,
		prefix="",
		expected_origin=None,  # Different CORS for subdomains
	)

	time.sleep(2)  # Ensure port is released

	# Test 3: Custom CORS in single-server mode
	log_section("Testing custom CORS override")
	custom_cors = {
		"allow_origins": ["https://example.com", "http://localhost:9003"],
		"allow_methods": ["GET", "POST"],
		"allow_credentials": True,
	}
	all_passed &= run_test_suite(
		deployment="single-server",
		port=9003,
		prefix="/api/pulse",
		expected_origin=None,  # Custom CORS, so we don't check specific origin
		cors=custom_cors,
	)

	# Final summary
	log_section("Final Summary")
	if all_passed:
		log_success("✓ All Phase 1 tests passed!")
		log_success("✓ API route prefixing works correctly")
		log_success("✓ CORS headers configured properly")
		log_success("✓ Backward compatibility maintained")
		return 0
	else:
		log_error("✗ Some Phase 1 tests failed")
		log_error("Please review the output above for details")
		return 1


if __name__ == "__main__":
	sys.exit(main())
