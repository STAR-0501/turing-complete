---
id: skill-dbg-2
name: Alias Must Share Scope With All Commands in a Build Block
description: AI agent building circuits with ADD and WIRE commands using aliases
tags: [debugging, alias, build]
---

### Skill-DBG-2: Alias Must Share Scope With All Commands in a Build Block
- **Context**: AI agent building circuits with `ADD <type> <x> <y> <alias>` then `WIRE <alias> ...`.
- **What**: Execute ALL build commands in a single `_execute_commands_with_alias()` call so the alias map is built incrementally per command.
- **Why**: Per-command execution resets the alias map each time, breaking `$last` and named alias references across wire commands.
- **Example**: Buffer all `<build>` lines, then `_execute_commands_with_alias(buffer)` once.
