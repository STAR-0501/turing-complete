---
id: skill-be-1
name: Atomic File Writes Prevent Corruption
description: Writing JSON/markdown state files on any platform
tags: [backend, io, atomic, persistence]
---

### Skill-BE-1: Atomic File Writes Prevent Corruption
- **Context**: Writing JSON/markdown state files on any platform.
- **What**: Always write to a temp file first, then `os.replace()` to atomically swap. Clean up stale `.tmp.*` files before writing.
- **Why**: Direct writes risk file corruption on crash or concurrent access. Atomic swap ensures the file is always in a valid state.
- **Example**: `_atomic_write_json()` / `_atomic_write_md()` pattern.
