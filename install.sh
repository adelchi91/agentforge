#!/usr/bin/env bash
set -euo pipefail

REPO="${AGENTFORGE_REPO:-https://github.com/adelchi91/agentforge}"
TARGET="${1:-claude}"
TMPDIR_WORK=$(mktemp -d)
SOURCE_ROOT=""

cleanup() { rm -rf "$TMPDIR_WORK"; }
trap cleanup EXIT

echo "Installing agentforge target: $TARGET"

prepare_source() {
  if [[ -n "${AGENTFORGE_SOURCE_DIR:-}" ]]; then
    SOURCE_ROOT="${AGENTFORGE_SOURCE_DIR%/}"
  elif [[ -d "$REPO" ]]; then
    SOURCE_ROOT="${REPO%/}"
  else
    git clone --depth 1 "$REPO" "$TMPDIR_WORK/agentforge" --quiet
    SOURCE_ROOT="$TMPDIR_WORK/agentforge"
  fi

  for dir in agents commands templates steps refs; do
    if [[ ! -d "$SOURCE_ROOT/$dir" ]]; then
      echo "Missing required source directory: $SOURCE_ROOT/$dir" >&2
      exit 1
    fi
  done
}

install_claude() {
  local dest=".claude"
  echo "Installing Claude bootstrap into $dest/ ..."
  mkdir -p "$dest"
  for dir in agents commands templates steps refs; do
    cp -r "$SOURCE_ROOT/$dir" "$dest/"
  done
  echo "Done. Open Claude Code in this directory and run /bootstrap to start."
}

install_codex() {
  local dest=".agents/skills/project-bootstrap"
  echo "Installing Codex bootstrap skill into $dest/ ..."
  if [[ ! -f "$SOURCE_ROOT/.agents/skills/project-bootstrap/SKILL.md" ]]; then
    echo "Missing Codex skill source: $SOURCE_ROOT/.agents/skills/project-bootstrap/SKILL.md" >&2
    exit 1
  fi
  mkdir -p "$dest/bootstrap"
  cp "$SOURCE_ROOT/.agents/skills/project-bootstrap/SKILL.md" "$dest/SKILL.md"
  for dir in agents commands templates steps refs; do
    cp -r "$SOURCE_ROOT/$dir" "$dest/bootstrap/"
  done
  echo "Done. Open Codex in this directory and invoke \$project-bootstrap to start."
}

prepare_source

case "$TARGET" in
  claude)
    install_claude
    ;;
  codex)
    install_codex
    ;;
  both)
    install_claude
    install_codex
    ;;
  *)
    echo "Usage: install.sh [claude|codex|both]" >&2
    exit 2
    ;;
esac
