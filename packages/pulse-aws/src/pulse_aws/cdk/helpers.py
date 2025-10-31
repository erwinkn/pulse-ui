from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Literal, overload

import aws_cdk as cdk


@overload
def cvalue(app: cdk.App, key: str, *, optional: Literal[False] = False) -> str: ...
@overload
def cvalue(app: cdk.App, key: str, *, optional: bool) -> str | None: ...
def cvalue(app: cdk.App, key: str, *, optional: bool = False) -> str | None:
	value = app.node.try_get_context(key) or os.getenv(key.upper())
	if not optional and not value:
		msg = f"Missing required CDK context value '{key}'"
		raise ValueError(msg)
	return value


def lst(value: str | None) -> Sequence[str] | None:
	if not value:
		return None
	return [item.strip() for item in value.split(",") if item.strip()]
