---
id: skill-arch-2
name: State Change Markers for Frontend Sync
description: SSE streaming from Flask to frontend canvas
tags: [architecture, sse, frontend, sync]
---

### Skill-ARCH-2: State Change Markers for Frontend Sync
- **Context**: SSE streaming from Flask to frontend canvas.
- **What**: After each successful state mutation command, yield `__TC_STATE_CHANGED__` marker. Frontend listens for this marker and re-fetches circuit state.
- **Why**: Without explicit markers, the frontend canvas shows stale data. The marker is the only reliable trigger for canvas refresh.
- **Example**: `yield STREAM_STATE_CHANGED_MARKER` after successful `add_element`/`add_wire`/`toggle_input`.
