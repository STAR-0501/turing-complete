---
id: skill-dbg-1
name: File Write Conflicts Under Concurrency
description: Windows environment, Flask with multiple concurrent request handlers accessing the same JSON file
tags: [debugging, windows, concurrency]
---

### Skill-DBG-1: File Write Conflicts Under Concurrency
- **Context**: Windows environment, Flask with multiple concurrent request handlers accessing the same JSON file (`circuit_data.json`, `MODULEs_data.json`).
- **What**: Use a `threading.Lock()` to serialize all file write operations. Never assume single-threaded access in a web server context.
- **Why**: Without a lock, concurrent `_atomic_write_json` calls cause "拒绝访问" (access denied) errors on Windows, corrupting data silently.
- **Example**: `_data_io_lock = threading.Lock()` + `_locked_write_json(path, data)` wrapper.
