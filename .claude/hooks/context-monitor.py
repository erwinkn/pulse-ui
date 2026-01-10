#!/usr/bin/env python3
"""
PostToolUse hook that monitors transcript size and informs agent about context usage.

Provides feedback about current context percentage. Agent uses this information
to decide when to save progress and stop (per prompt instructions).
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
	context_size = 200_000  # Opus context window
	percent = (tokens / context_size) * 100

	# Just inform the agent about current context usage
	print(
		json.dumps({"message": f"📊 Context usage: {percent:.0f}% ({tokens:,} tokens)"})
	)

	sys.exit(0)


if __name__ == "__main__":
	main()
