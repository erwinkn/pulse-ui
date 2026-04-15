from __future__ import annotations

import asyncio
import secrets
import tempfile
from pathlib import Path

from pulse_railway.config import DockerBuild
from pulse_railway.constants import DEFAULT_ROUTER_PORT
from pulse_railway.errors import DeploymentError


async def _run_command(*args: str, cwd: Path | None = None) -> None:
	process = await asyncio.create_subprocess_exec(
		*args,
		cwd=str(cwd) if cwd is not None else None,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	if process.returncode != 0:
		raise DeploymentError(
			f"command failed ({' '.join(args)}):\n{stdout.decode()}{stderr.decode()}"
		)


def default_image_ref(*, image_repository: str | None, prefix: str) -> str:
	if image_repository:
		return f"{image_repository}:{prefix}"
	return f"ttl.sh/pulse-railway-{prefix}-{secrets.token_hex(4)}:24h"


async def build_and_push_image(
	*,
	docker: DockerBuild,
	image_ref: str,
) -> str:
	command = [
		"docker",
		"buildx",
		"build",
		"--push",
		"--platform",
		docker.platform,
		"-t",
		image_ref,
		"-f",
		str(docker.dockerfile_path),
	]
	for key, value in sorted(docker.build_args.items()):
		command.extend(["--build-arg", f"{key}={value}"])
	command.append(str(docker.context_path))
	await _run_command(*command)
	return image_ref


def _workspace_root() -> Path | None:
	for parent in Path(__file__).resolve().parents:
		if (parent / "packages" / "pulse-railway" / "pyproject.toml").exists():
			return parent
	return None


def _router_dockerfile() -> str:
	workspace_root = _workspace_root()
	if workspace_root is None:
		return "\n".join(
			[
				"FROM python:3.12-slim",
				"COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv",
				"RUN uv pip install --system pulse-railway",
				f"EXPOSE {DEFAULT_ROUTER_PORT}",
				'CMD ["uvicorn", "pulse_railway.router:build_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]',
			]
		)
	return "\n".join(
		[
			"FROM python:3.12-slim",
			"COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv",
			"WORKDIR /src",
			"COPY packages/pulse/python /src/packages/pulse/python",
			"COPY packages/pulse-railway /src/packages/pulse-railway",
			"RUN uv pip install --system /src/packages/pulse/python /src/packages/pulse-railway",
			f"EXPOSE {DEFAULT_ROUTER_PORT}",
			'CMD ["uvicorn", "pulse_railway.router:build_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]',
		]
	)


async def build_router_image(*, image_ref: str) -> str:
	workspace_root = _workspace_root()
	context = workspace_root if workspace_root is not None else Path(tempfile.mkdtemp())
	with tempfile.NamedTemporaryFile("w", suffix=".Dockerfile", delete=False) as handle:
		handle.write(_router_dockerfile())
		dockerfile_path = Path(handle.name)
	try:
		command = [
			"docker",
			"buildx",
			"build",
			"--push",
			"--platform",
			"linux/amd64",
			"-t",
			image_ref,
			"-f",
			str(dockerfile_path),
			str(context),
		]
		await _run_command(*command)
		return image_ref
	finally:
		dockerfile_path.unlink(missing_ok=True)


__all__ = ["build_and_push_image", "build_router_image", "default_image_ref"]
