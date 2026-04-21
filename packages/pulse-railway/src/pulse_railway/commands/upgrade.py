from __future__ import annotations

import argparse
import asyncio
from typing import Any


def _add_upgrade_args(parser: argparse.ArgumentParser) -> None:
	parser.description = (
		"No-op placeholder. Run `pulse-railway init` to manage the baseline stack."
	)


async def _run_upgrade(args: argparse.Namespace) -> int:
	_ = args
	return 0


add_upgrade_args = _add_upgrade_args
run_upgrade = _run_upgrade


def register(subparsers: Any) -> None:
	upgrade_parser = subparsers.add_parser(
		"upgrade",
		help="No-op placeholder for future stack migrations.",
	)
	_add_upgrade_args(upgrade_parser)


def main(args: argparse.Namespace) -> int:
	return asyncio.run(_run_upgrade(args))
