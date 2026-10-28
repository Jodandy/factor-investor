#!/bin/bash
# PostToolUse hook: after editing Python under src/factor_investor/ or tests/,
# run the fast, database-free test suite (unit tests + engine integrity tests).
# Exit 2 sends the failure output back to Claude (CLAUDE.md invariant 8).

file=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')

case "$file" in
  */src/factor_investor/*.py | */tests/*.py) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

output=$(uv run pytest tests/unit tests/integrity/test_backtest_engine.py -q -p no:warnings -x 2>&1)
status=$?

if [ $status -ne 0 ]; then
  echo "Fast test suite FAILED after editing $file:" >&2
  echo "$output" | tail -40 >&2
  exit 2
fi
exit 0
