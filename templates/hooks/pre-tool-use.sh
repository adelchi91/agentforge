#!/bin/bash
# pre-tool-use.sh — Safety guardrail hook
# exit 2 = hard block (unconditional — Claude Code cannot override)
# exit 1 = soft warning (Claude Code may continue)
# exit 0 = allow

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [[ "$TOOL_NAME" == "Bash" ]]; then

  # Block destructive commands
  if echo "$TOOL_INPUT" | grep -qE "rm -rf|git push --force|DROP TABLE|truncate"; then
    echo "ERROR: Destructive command blocked by pre-tool-use hook." >&2
    echo "Command: $TOOL_INPUT" >&2
    exit 2
  fi

  # Require STORY reference in git commit messages
  if echo "$TOOL_INPUT" | grep -q "git commit"; then
    MSG=$(echo "$TOOL_INPUT" | grep -o '\-m "[^"]*"' | head -1)
    if [[ -n "$MSG" ]] && ! echo "$MSG" | grep -qE "STORY-[0-9]+"; then
      echo "ERROR: Commit message must reference a STORY-XXX." >&2
      echo "Example: git commit -m 'STORY-001: add pyproject.toml'" >&2
      exit 2
    fi
  fi

  # Block git push without story reference in latest commit
  if echo "$TOOL_INPUT" | grep -q "git push" && ! echo "$TOOL_INPUT" | grep -q "force"; then
    LAST_MSG=$(git log -1 --format="%s" 2>/dev/null || echo "")
    if [[ -n "$LAST_MSG" ]] && ! echo "$LAST_MSG" | grep -qE "STORY-[0-9]+"; then
      echo "ERROR: Latest commit does not reference a STORY-XXX. Push blocked." >&2
      exit 2
    fi
  fi

fi

exit 0
