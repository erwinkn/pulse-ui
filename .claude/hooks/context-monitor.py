#!/usr/bin/env python3
"""
PostToolUse hook that monitors transcript size and provides feedback when context is critical.

When context usage hits 80%, returns {"decision": "block", "reason": "..."} which
Claude sees as feedback after the tool completes, instructing it to save progress and stop.
"""

import json
import os
import sys


def estimate_tokens(transcript_path: str) -> int:
	"""Rough token estimate: ~4 chars per token."""
	if not os.path.exists(transcript_path):
		return 0
	size = os.path.getsize(transcript_path)
	return size // 4


def main():
	input_data = json.load(sys.stdin)
	transcript_path = input_data.get("transcript_path", "")

	if not transcript_path:
		sys.exit(0)

	tokens = estimate_tokens(transcript_path)

	# Opus has 200k context. Critical at 160k (80%)
	CRITICAL_THRESHOLD = 160_000

	if tokens >= CRITICAL_THRESHOLD:
		# Provide feedback to Claude - it will see this reason
		print(
			json.dumps(
				{
					"decision": "block",
					"reason": f"🛑 CONTEXT CRITICAL ({tokens:,} tokens, ~80%). "
					"You must stop now to avoid compaction. "
					"1) Write partial progress to progress.txt under '## In Progress' section, "
					"2) Do NOT mark task as passed in prd.json, "
					"3) Commit with 'wip: [ID] - partial progress', "
					"4) Stop immediately. Next iteration will continue with fresh context.",
				}
			)
		)

	sys.exit(0)


if __name__ == "__main__":
	main()
