# Walkthrough — pycalc (Python CLI Calculator)

A complete end-to-end example of running `/bootstrap` on a greenfield Python project.
This documents an actual session run against an empty directory.

---

## Setup

```bash
mkdir ~/pycalc && cd ~/pycalc

# Install agentforge
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash
# Output: Installing agentforge into .claude/ ...
#         Done. Open Claude Code in this directory and run /bootstrap to start.

# Open Claude Code
claude
```

---

## Running /bootstrap

Type `/bootstrap` then `OK` to begin.

```
── Project Bootstrap ──────────────────────────────────────────────
  claude-project-bootstrap v1.0.0

  I'll scaffold a complete Claude Code agentic development
  environment for this project in 5 steps:

    Step 1 — Project context & codebase scan
    Step 2 — Roadmap planning
    Step 3 — Persona definition
    Step 4 — Story generation
    Step 5 — File scaffolding

  Estimated time: 10–15 minutes.
  Nothing is written to disk until Step 5 and you type GO.

  Type OK to begin, or CANCEL to exit.
───────────────────────────────────────────────────────────────────
```

When prompted for permissions during the session, choose **"Yes, allow all edits during this session"** to avoid approval prompts on every file write.

---

## Step 1 — Project context

The interviewer asks one question at a time:

| Question | Answer given |
|---|---|
| What is the name of this project? | `pycalc` |
| Describe it in 2–3 sentences: what does it do, who uses it? | `pycalc — a CLI calculator supporting +, -, *, / with history. For personal use and as a test project.` |
| What is the primary programming language and stack? | `Python 3.11+, uv for package management, distributed as a pip-installable CLI tool` |
| Does this project have existing code? [Y/N] | `N` |
| What is the main deliverable at the end of this project? | `A pip-installable CLI tool: pycalc "2+2" works from any terminal, with interactive REPL mode and calculation history` |
| Are there any hard constraints? | `no` |
| Is there a golden rule? | `The test suite must never break during development` |

Type `OK` to move to Step 2.

---

## Step 2 — Roadmap

The interviewer first asks whether you already have a structure in mind:

> "Do you already have an idea of how you'd like to structure this project — phases, milestones, or a rough plan? Or should I propose one based on what you've told me?"

Answer: `Propose one — I have no prior structure in mind.`

The interviewer then proposes a 4-phase roadmap:

| Phase | Name | Description | Est. stories |
|---|---|---|---|
| 1 | Foundation & Scaffolding | Package structure, pyproject.toml, uv environment, CLI entry point skeleton, test harness | 3 |
| 2 | Core Calculator Engine | Expression parser and evaluator: +, -, *, / with operator precedence and error handling | 4 |
| 3 | CLI, REPL & History | One-shot CLI mode, interactive REPL, persistent calculation history | 5 |
| 4 | Polish & Distribution | PyPI packaging, user-facing README, end-to-end install validation | 3 |

Type `OK` to accept, or describe changes in natural language (e.g. "merge phases 3 and 4").

---

## Step 3 — Personas

The interviewer proposes 4 agents:

| Agent | Model | Scope | Role |
|---|---|---|---|
| final-judge | claude-sonnet-4-6 | full repo | Approval authority — reviews and accepts/rejects completed stories |
| architect | claude-sonnet-4-6 | read + write docs/stories | Writes design decisions, ADRs, story definitions |
| dev | claude-haiku-4-5 | src/ + tests/ | Implements stories: Python source and unit tests |
| tester | claude-haiku-4-5 | read + bash | Runs test suite, reports PASS/FAIL, uses Explore to locate test files |

Type `OK` to accept, or request additional agents (e.g. "a packaging agent", "a docs writer").

---

## Step 4 — Stories

When asked "Review each story individually? [Y/N]", type `N` to generate all at once.

The planner generates 15 stories across 4 phases:

| Story | Phase | Agent | Title |
|---|---|---|---|
| STORY-001 | 1 — Foundation | architect | Define package structure and pyproject.toml spec |
| STORY-002 | 1 — Foundation | dev | Scaffold Python package, pyproject.toml, and CLI entry point skeleton |
| STORY-003 | 1 — Foundation | tester | Verify package installs and entry point runs |
| STORY-004 | 2 — Core Engine | dev | Implement expression tokenizer |
| STORY-005 | 2 — Core Engine | dev | Implement expression parser with operator precedence |
| STORY-006 | 2 — Core Engine | dev | Implement evaluator with error handling |
| STORY-007 | 2 — Core Engine | tester | Run full engine test suite and report |
| STORY-008 | 3 — CLI & History | dev | Implement one-shot CLI mode |
| STORY-009 | 3 — CLI & History | dev | Implement interactive REPL mode |
| STORY-010 | 3 — CLI & History | dev | Implement in-session calculation history |
| STORY-011 | 3 — CLI & History | dev | Implement persistent calculation history |
| STORY-012 | 3 — CLI & History | tester | Run full CLI, REPL, and history test suite |
| STORY-013 | 4 — Distribution | architect | Write README with usage examples |
| STORY-014 | 4 — Distribution | dev | Finalise packaging for PyPI |
| STORY-015 | 4 — Distribution | tester | Validate end-to-end install and smoke test |

Before typing `OK`, verify the stories:
```bash
# No unfilled placeholders
grep -r '{{' .bootstrap/stories/

# Spot-check a story's verification commands
cat .bootstrap/stories/STORY-002.md
```

Type `OK` to move to Step 5.

---

## Step 5 — Scaffold

The scaffolder shows a CHECKPOINT with the complete file tree, then waits for `GO`:

```
.claude/
├── CLAUDE.md
├── settings.json
├── agents/
│   ├── final-judge.md     (claude-sonnet-4-6)
│   ├── architect.md       (claude-sonnet-4-6)
│   ├── dev.md             (claude-haiku-4-5)
│   └── tester.md          (claude-haiku-4-5)
├── skills/
│   ├── python-packaging.md
│   └── expression-parsing.md
├── hooks/
│   ├── pre-tool-use.sh
│   ├── post-tool-use.sh
│   └── stop.sh
└── stories/
    └── STORY-001.md … STORY-015.md

project_context.md
roadmap.md
.gitignore
```

Type `GO`. After scaffolding completes, verify:

```bash
# No unfilled placeholders
grep -r '{{' .claude/

# Hooks are executable
ls -l .claude/hooks/
```

> **Note:** during scaffolding you may see `PostToolUse:Write hook error — No such file or directory`.
> This is harmless — the hook fires before the hook file itself has been written. It resolves once
> scaffolding completes.

---

## Starting development

```
Work on STORY-001.
```

The `architect` agent takes over and designs the package structure. Each subsequent story follows the same pattern:

1. `"Work on STORY-XXX."` — the assigned agent executes
2. `"Test STORY-XXX."` — the tester agent runs verification
3. Review output and approve before moving to the next story

Sub-commands available at any time:
- `/story` — add a new story to an existing phase
- `/add-agent` — add a new agent
- `/project-review` — update roadmap or personas
