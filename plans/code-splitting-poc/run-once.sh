#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Running single iteration (for testing PRD quality)"
echo "Plan: $SCRIPT_DIR"
echo ""

cat "$SCRIPT_DIR/prompt.md" | claude --dangerously-skip-permissions

echo ""
echo "Single iteration complete."
echo "Check: $SCRIPT_DIR/prd.json and $SCRIPT_DIR/progress.txt"
