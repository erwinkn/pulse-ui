#!/usr/bin/env python3
"""Teardown baseline infrastructure deployed by pulse-aws."""

from __future__ import annotations

from pulse_aws.cli import teardown_main

if __name__ == "__main__":
	raise SystemExit(teardown_main())
