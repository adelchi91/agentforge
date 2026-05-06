# Walkthrough — pycalc (Python CLI Calculator)

A complete end-to-end example of running `/bootstrap` on a greenfield Python project.
This documents an actual session run against an empty directory.

---

## Setup

```bash
mkdir ~/pycalc && cd ~/pycalc

# Install agentforge
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash

# Open Claude Code
claude .
```

---

## Step 1 — Project context

Run `/bootstrap` and type `OK` to begin. The interviewer asks:

**What is this project?**
```
pycalc — a CLI calculator supporting +, -, *, / with history. For personal use and as a test project.
```

**Primary stack?**
```
python
```

**Target Python version and packaging preferences?**
```
Python 3.11+, uv for package management, distributed as a pip-installable CLI tool
```

**Structure preferences?**
```
## Core logic
- Operations: +, -, *, /, power, sqrt
- Input validation with clear error messages
- Float and integer support

## CLI
- Interactive REPL mode: type expressions, get results
- Single expression mode: `pycalc "2 + 2"`
- `--precision N` flag to control decimal places

## History
- Save last N calculations to ~/.pycalc_history
- `pycalc --history` to display past results
- `pycalc --clear-history` to wipe it

## Distribution
- Installable via `pip install pycalc` or `uv add pycalc`
- Single `pycalc` entry point
```

Type `OK` to move to Step 2.

---

## Step 2 — Roadmap

The interviewer proposes a phase plan. For pycalc it produced:

| Phase | Name | Stories |
|---|---|---|
| 1 | Core Logic | 4 |
| 2 | CLI | 3 |
| 3 | History | 3 |
| 4 | Distribution | 1 |

Type `OK` to accept, or edit in natural language ("merge phases 3 and 4", "add a docs phase").

---

## Step 3 — Personas

The interviewer proposes agents based on the roadmap:

| Agent | Model | Scope | Role |
|---|---|---|---|
| architect | claude-sonnet-4-6 | read + write docs | Design module structure, ADRs |
| dev | claude-haiku-4-5 | src/, tests/ | Implementation |
| tester | claude-haiku-4-5 | read + bash | Run verification, write reports |
| final-judge | claude-sonnet-4-6 | full repo read-only | Approval authority |

Type `OK` to accept.

---

## Step 4 — Stories

The planner generates 12 stories across 4 phases:

| Story | Phase | Agent | Summary |
|---|---|---|---|
| STORY-001 | 1 — Core Logic | architect | Design module structure, public API, error hierarchy |
| STORY-002 | 1 — Core Logic | dev | Scaffold project: pyproject.toml, src layout, empty modules |
| STORY-003 | 1 — Core Logic | dev | Implement six arithmetic operations in calc.py |
| STORY-004 | 1 — Core Logic | dev | Expression parser and validator in validator.py |
| STORY-005 | 1 — Core Logic | tester | Pytest suite for calc.py and validator.py (≥20 tests) |
| STORY-006 | 2 — CLI | dev | Single-expression mode with --precision flag |
| STORY-007 | 2 — CLI | dev | Interactive REPL mode with Ctrl-C/Ctrl-D handling |
| STORY-008 | 2 — CLI | tester | CLI integration tests via subprocess (≥12 tests) |
| STORY-009 | 3 — History | dev | History storage module: append, read, clear, capped at N |
| STORY-010 | 3 — History | dev | Wire history into CLI: --history / --clear-history |
| STORY-011 | 3 — History | tester | History module and CLI flag tests (tmp_path isolation) |
| STORY-012 | 4 — Distribution | final-judge | Build wheel, install in clean venv, full test run, SIGN-OFF.md |

Before typing `GO`, verify the stories look sensible:
```bash
# Check no unfilled placeholders
grep -r '{{' .bootstrap/stories/

# Spot-check verification commands are real bash
cat .bootstrap/stories/STORY-001.md
```

Type `OK` to move to Step 5.

---

## Step 5 — Scaffold

Type `GO`. The scaffolder writes 24 files:

```
pycalc/
├── CLAUDE.md
├── roadmap.md
├── project_context.md
├── .gitignore
└── .claude/
    ├── settings.json
    ├── agents/
    │   ├── architect.md       (claude-sonnet-4-6)
    │   ├── dev.md             (claude-haiku-4-5)
    │   ├── tester.md          (claude-haiku-4-5)
    │   └── final-judge.md     (claude-sonnet-4-6)
    ├── skills/
    │   ├── core-logic/arithmetic.md
    │   ├── cli/argparse-patterns.md
    │   ├── history/file-persistence.md
    │   └── distribution/packaging.md
    ├── hooks/
    │   ├── pre-tool-use.sh
    │   ├── post-tool-use.sh
    │   └── stop.sh
    └── stories/
        └── STORY-001.md … STORY-012.md
```

Final check:
```bash
grep -r '{{' .claude/    # must return empty
ls -l .claude/hooks/     # all .sh must be -rwxr-xr-x
```

---

## Starting development

```
Work on STORY-001.
```

The `architect` agent takes over, designs the module structure, and hands off to `dev` for STORY-002.

Each story follows the same pattern:
1. `"Work on STORY-XXX."` — the assigned agent executes
2. `"Test STORY-XXX."` — the tester agent runs verification
3. Review and approve before moving to the next story
