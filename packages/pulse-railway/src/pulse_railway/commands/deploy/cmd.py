from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Any

from pulse_railway.commands.deploy.common import (
	add_shared_deploy_args,
	resolve_deploy_command,
)
from pulse_railway.commands.deploy.image import run_deploy_image
from pulse_railway.commands.deploy.source import run_deploy_source


def _add_deploy_args(parser: argparse.ArgumentParser) -> None:
	add_shared_deploy_args(parser)


async def _run_deploy(args: argparse.Namespace) -> int:
	command = await resolve_deploy_command(args)
	if command.mode == "image":
		result = await run_deploy_image(command)
	else:
		result = await run_deploy_source(command)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


add_deploy_args = _add_deploy_args
run_deploy = _run_deploy


def register(subparsers: Any) -> None:
	deploy_parser = subparsers.add_parser(
		"deploy",
		help="Deploy a new application version onto an existing pulse-railway stack.",
	)
	_add_deploy_args(deploy_parser)


def main(args: argparse.Namespace) -> int:
	return asyncio.run(_run_deploy(args))
