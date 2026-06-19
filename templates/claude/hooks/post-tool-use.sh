#!/bin/bash
# post-tool-use.sh — Auto-lint on Write
# Runs after every file write. Lints Python files with ruff if available.

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [[ "$TOOL_NAME" == "Write" ]]; then
  # Extract file path from tool input
  FILE=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('path', ''))
except:
    print('')
" 2>/dev/null)

  if [[ -n "$FILE" && "$FILE" == *.py ]]; then
    if command -v ruff &>/dev/null; then
      ruff check "$FILE" --fix --quiet 2>/dev/null || true
    fi
  fi

  if [[ -n "$FILE" && ("$FILE" == *.js || "$FILE" == *.ts) ]]; then
    if command -v eslint &>/dev/null; then
      eslint "$FILE" --fix --quiet 2>/dev/null || true
    fi
  fi
fi

exit 0
