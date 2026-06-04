---
id: skill-arch-3
name: Session Continuity via Persisted Plan/Summary
description: Multi-round AI agent sessions that may be interrupted
tags: [architecture, session, persistence]
---

### Skill-ARCH-3: Session Continuity via Persisted Plan/Summary
- **Context**: Multi-round AI agent sessions that may be interrupted.
- **What**: Persist `<plan>` content to `plan.md` and `<sum>` content to `summary.md` after each round. Load both at session start.
- **Why**: Enables recovery from interruption, gives AI full context across rounds, and supports long-running circuit building tasks.
- **Example**: `_atomic_write_md(PLAN_FILE, plan_text)` + `_atomic_write_md(SUMMARY_FILE, sum_text)`.
