---
id: skill-arch-1
name: 5-Mode Agent Loop Structure
description: AI agent performing autonomous circuit building
tags: [architecture, agent, loop]
---

### Skill-ARCH-1: 5-Mode Agent Loop Structure
- **Context**: AI agent performing autonomous circuit building.
- **What**: Always use the cycle: `<think>` (analyze) → `<plan>` (break down) → `<build>` (execute commands) → `<observe>` (test/verify) → `<sum>` (summarize). Repeat until `<done>true</done>`.
- **Why**: This separates reasoning from action, enables verification, and provides session continuity via plan.md/summary.md persistence.
- **Example**: Each round produces all 5 sections; system processes each section independently.
