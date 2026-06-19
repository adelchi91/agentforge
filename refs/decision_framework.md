# Decision Framework

When creating a new file or rule, first read the selected target platform
(`CLAUDE` or `CODEX`), then ask these four questions in order:

1. Must this be enforced unconditionally (cannot be argued away by the agent)?
   YES → Hook (`.claude/hooks` or `.codex/hooks`)   NO → continue

2. Does this define who an agent IS and what it can do?
   YES → Claude `agents/*.md`; Codex `.codex/agents/*.toml`   NO → continue

3. Does this define what an agent KNOWS?
   YES → Claude `skills/*.md`; Codex `.agents/skills/*/SKILL.md`   NO → continue

4. Does this apply to every session without exception?
   YES → Claude `CLAUDE.md`; Codex `AGENTS.md`       NO → story file or inline context
