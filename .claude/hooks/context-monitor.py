#!/usr/bin/env python3
"""
PostToolUse hook that monitors transcript size and provides feedback about context limits.

At 60%: Warns agent to consider updating progress.txt
At 80%: Blocks non-save operations, requires agent to update progress.txt before continuing
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
	tool_name = input_data.get("tool_name", "")

	if not transcript_path:
		sys.exit(0)

	tokens = estimate_tokens(transcript_path)

	# Opus has 200k context
	WARN_THRESHOLD = 120_000  # 60%
	CRITICAL_THRESHOLD = 160_000  # 80%

	if tokens >= CRITICAL_THRESHOLD:
		# At 80%, only allow save operations (Read/Write/Edit/Bash for git)
		# This ensures agent can update progress.txt before stopping
		if tool_name in ("Read", "Write", "Edit"):
			sys.exit(0)
		if tool_name == "Bash":
			command = input_data.get("tool_input", {}).get("command", "")
			if "git" in command:
				sys.exit(0)

		# Block all other operations
		print(
			json.dumps(
				{
					"decision": "block",
					"reason": f"🛑 CONTEXT CRITICAL ({tokens:,} tokens, ~80%). "
					"You MUST update progress.txt NOW before stopping. "
					"Required actions: "
					"1) Read progress.txt, 2) Write '## In Progress' section with current state, "
					"3) Do NOT mark task as passed in prd.json, "
					"4) Commit with 'wip: [ID] - partial progress', "
					"5) Stop immediately. Next iteration will continue with fresh context.",
				}
			)
		)
	elif tokens >= WARN_THRESHOLD:
		# At 60%, warn but don't block - just provide feedback
		print(
			json.dumps(
				{
					"decision": "block",
					"reason": f"⚠️ Context at {tokens:,} tokens (~60%). "
					"Consider updating progress.txt soon with current progress. "
					"If task is close to done, continue. Otherwise, wrap up and stop.",
				}
			)
		)

	sys.exit(0)


if __name__ == "__main__":
	main()
