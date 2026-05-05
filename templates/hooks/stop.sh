#!/bin/bash
# stop.sh — Session summary on Stop event
# Fires when Claude Code session ends. Logs to .claude/session-log.txt

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
STORY=$(git log -1 --format="%s" 2>/dev/null | grep -o "STORY-[0-9]*" || echo "UNKNOWN")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

LOG_FILE=".claude/session-log.txt"
mkdir -p .claude

echo "────────────────────────────────────────" >> "$LOG_FILE"
echo "SESSION END: $TIMESTAMP" >> "$LOG_FILE"
echo "Story:       $STORY" >> "$LOG_FILE"
echo "Branch:      $BRANCH" >> "$LOG_FILE"
echo "────────────────────────────────────────" >> "$LOG_FILE"

exit 0
