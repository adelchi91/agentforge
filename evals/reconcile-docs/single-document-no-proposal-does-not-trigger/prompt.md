---
name: "reconcile-docs does not fire for a plain summarization request with no proposal to compare"
tags: [reconcile-docs, not-a-trigger]
plugins: ["agentforge"]
runs: 3
max_turns: 4
timeout_seconds: 90
---
Here is our PRD for the notifications feature:

```
# Notifications PRD

1. Users can mark a notification as read.
2. Users can mute a notification category.
3. Admins can see an audit log of muted categories.
```

Can you summarize this PRD in two sentences for a status update?
