#!/bin/bash
set -e

MAX_ITERATIONS=${1:-25}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Ralph Loop"
echo "Plan: $SCRIPT_DIR"
echo "Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "═══════════════════════════════════════"
  echo "  Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════"

  OUTPUT=$(cat "$SCRIPT_DIR/prompt.md" \
    | claude --dangerously-skip-permissions 2>&1 \
    | tee /dev/stderr) || true

  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "✅ All features complete!"
    exit 0
  fi

  sleep 2
done

echo ""
echo "⚠️ Max iterations reached ($MAX_ITERATIONS)"
echo "Check progress: cat $SCRIPT_DIR/progress.txt"
exit 1
