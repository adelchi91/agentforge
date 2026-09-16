# scripts/

Python modules backing AgentForge's skills and hooks (`config.py`,
`context.py`, `git_policy.py`, `scope_policy.py`, `work_items.py`, ...),
added starting with STORY-004.

These run from the installed plugin cache, not from a copy inside the target
project. Any skill or hook that invokes a script here must reference it
through `${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` — never assume it was
copied into the project being worked on.
