from __future__ import annotations

import asyncio
from pathlib import Path

from pulse_railway.config import DockerBuild
from pulse_railway.errors import DeploymentError

OFFICIAL_JANITOR_IMAGE_REPOSITORY = "ghcr.io/erwinkn/pulse-railway-janitor"
OFFICIAL_ROUTER_IMAGE_REPOSITORY = "ghcr.io/erwinkn/pulse-railway-router"
OFFICIAL_RUNTIME_IMAGE_VERSION = "0.3.11"


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


def image_ref(*, image_repository: str | None, prefix: str) -> str:
	if not image_repository:
		raise DeploymentError("image mode requires an image repository")
	return f"{image_repository}:{prefix}"


def official_router_image_ref(*, version: str | None = None) -> str:
	return f"{OFFICIAL_ROUTER_IMAGE_REPOSITORY}:{version or OFFICIAL_RUNTIME_IMAGE_VERSION}"


def official_janitor_image_ref(*, version: str | None = None) -> str:
	return f"{OFFICIAL_JANITOR_IMAGE_REPOSITORY}:{version or OFFICIAL_RUNTIME_IMAGE_VERSION}"


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


__all__ = [
	"OFFICIAL_JANITOR_IMAGE_REPOSITORY",
	"OFFICIAL_RUNTIME_IMAGE_VERSION",
	"OFFICIAL_ROUTER_IMAGE_REPOSITORY",
	"build_and_push_image",
	"image_ref",
	"official_janitor_image_ref",
	"official_router_image_ref",
]
