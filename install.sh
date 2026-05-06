#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/adelchi91/agentforge"
DEST=".claude"
TMPDIR_WORK=$(mktemp -d)

cleanup() { rm -rf "$TMPDIR_WORK"; }
trap cleanup EXIT

echo "Installing agentforge into $DEST/ ..."

git clone --depth 1 "$REPO" "$TMPDIR_WORK/agentforge" --quiet

mkdir -p "$DEST"

for dir in agents commands templates steps refs; do
  cp -r "$TMPDIR_WORK/agentforge/$dir" "$DEST/"
done

echo "Done. Open Claude Code in this directory and run /bootstrap to start."
