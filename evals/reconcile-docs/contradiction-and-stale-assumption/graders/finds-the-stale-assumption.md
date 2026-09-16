---
type: llm
criteria: "The response identifies, as a stale assumption (not as a plain contradiction), that the spec's reliance on ADR-0012 ('refund amounts stored in USD cents') is outdated because ADR-0031 (dated 2026-06-01) explicitly supersedes ADR-0012 and requires amounts to be stored in the customer's local currency instead. The finding should point at ADR-0031 as the superseding source."
target: last_message
---
Checks the skill's stale-assumption detection, a category distinct from
both contradiction and omission/exclusion that STORY-016 also requires.
