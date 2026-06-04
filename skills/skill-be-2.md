---
id: skill-be-2
name: Streaming Response Context Must Stay Alive
description: Flask SSE endpoints that execute long-running agent loops
tags: [backend, sse, streaming, flask]
---

### Skill-BE-2: Streaming Response Context Must Stay Alive
- **Context**: Flask SSE endpoints that execute long-running agent loops.
- **What**: The `request` context and `g` object are NOT available in background threads or streaming generators after the request handler returns. Pass all needed context explicitly as module parameters.
- **Why**: Accessing `request` or `g` inside a generator that yields after the handler exits causes "Working outside of request context" RuntimeError.
- **Example**: Extract `user_message` from `request.json` before entering the generator, pass as parameter.
