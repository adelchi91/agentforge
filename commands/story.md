---
name: story
description: >
  Add a new story to an existing phase in a bootstrapped project.
  Triggers on: "add a story", "new story", "create a story", "I need a new story",
  "/story"
agent: planner
---

## Purpose

Add a new story to an existing project phase without re-running the full bootstrap.
Use this when new work is identified after the initial bootstrap session.

## Procedure

1. Read `project_context.md`, `roadmap.md`, and all existing `.claude/stories/STORY-XXX.md` files
2. Ask: "Which phase does this story belong to?" (show existing phases from `roadmap.md`)
3. Ask: "Describe what needs to be done in 2–3 sentences."
4. Ask: "Which agent will handle this?" (show existing agents from `.claude/agents/`)
5. Determine the next story number: `max(existing STORY-NNN) + 1`
6. Generate the story following `templates/story.md`
7. Show the complete story and ask:

```
Write to .claude/stories/STORY-NNN.md? [GO / CANCEL]
```

## Rules

- The new story ID follows existing sequential numbering (STORY-001, STORY-002, ...)
- The `Depends on:` field must reference an existing story or be `none`
- All verification commands must be real runnable shell commands — never prose
- Fill ALL fields from the story template — no field may be left empty or as a placeholder
- The `Out of scope` section is mandatory

## On GO

Write the story to `.claude/stories/STORY-NNN.md` and display:
```
✓ STORY-NNN written to .claude/stories/STORY-NNN.md

Start it with: "Work on STORY-NNN."
```

## On CANCEL

Display: "No story written." and exit cleanly.
