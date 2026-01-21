#!/usr/bin/env python3
"""Deploy a Pulse app to AWS ECS with baseline infrastructure."""

from __future__ import annotations

from pulse_aws.cli import deploy_main

if __name__ == "__main__":
	raise SystemExit(deploy_main())
