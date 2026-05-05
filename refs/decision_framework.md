# Decision Framework

When creating a new file or rule, ask these four questions in order:

1. Must this be enforced unconditionally (cannot be argued away by Claude)?
   YES → Hook (exit 2)   NO → continue

2. Does this define who an agent IS and what it can do?
   YES → agents/*.md     NO → continue

3. Does this define what an agent KNOWS?
   YES → skills/*.md     NO → continue

4. Does this apply to every session without exception?
   YES → CLAUDE.md       NO → story file or inline context
