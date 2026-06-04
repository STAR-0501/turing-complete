---
id: skill-dbg-3
name: Dual Execution Paths Cause Repeats
description: Streaming command executor and post-hoc fallback both run on the same LLM output
tags: [debugging, streaming, execution]
---

### Skill-DBG-3: Dual Execution Paths Cause Repeats
- **Context**: Streaming command executor (`_feed_stream_commands`) and post-hoc fallback (`_execute_commands_text`) both run on the same LLM output.
- **What**: Track whether streaming executed any commands. If yes, skip post-hoc fallback entirely.
- **Why**: Both paths operating on the same build tags cause duplicate circuit elements and broken state.
- **Example**: `if executed_command_count > 0: skip post-hoc`.
