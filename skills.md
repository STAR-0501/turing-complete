# Agent Skills (Self-Evolving Knowledge Base)

_Last updated: 2026-06-04_
_Total skills: 11_

> Skills are distilled, general-purpose knowledge extracted from agent work sessions.
> Each skill should be concise, abstract, and broadly applicable.
> When you discover universal insight, add it here for future sessions.

---

## Debugging

### Skill-DBG-1: File Write Conflicts Under Concurrency
- **Context**: Windows environment, Flask with multiple concurrent request handlers accessing the same JSON file (`circuit_data.json`, `MODULEs_data.json`).
- **What**: Use a `threading.Lock()` to serialize all file write operations. Never assume single-threaded access in a web server context.
- **Why**: Without a lock, concurrent `_atomic_write_json` calls cause "拒绝访问" (access denied) errors on Windows, corrupting data silently.
- **Example**: `_data_io_lock = threading.Lock()` + `_locked_write_json(path, data)` wrapper.

### Skill-DBG-2: Alias Must Share Scope With All Commands in a Build Block
- **Context**: AI agent building circuits with `ADD <type> <x> <y> <alias>` then `WIRE <alias> ...`.
- **What**: Execute ALL build commands in a single `_execute_commands_with_alias()` call so the alias map is built incrementally per command.
- **Why**: Per-command execution resets the alias map each time, breaking `$last` and named alias references across wire commands.
- **Example**: Buffer all `<build>` lines, then `_execute_commands_with_alias(buffer)` once.

### Skill-DBG-3: Dual Execution Paths Cause Repeats
- **Context**: Streaming command executor (`_feed_stream_commands`) and post-hoc fallback (`_execute_commands_text`) both run on the same LLM output.
- **What**: Track whether streaming executed any commands. If yes, skip post-hoc fallback entirely.
- **Why**: Both paths operating on the same build tags cause duplicate circuit elements and broken state.
- **Example**: `if executed_command_count > 0: skip post-hoc`.

---

## Architecture

### Skill-ARCH-1: 5-Mode Agent Loop Structure
- **Context**: AI agent performing autonomous circuit building.
- **What**: Always use the cycle: `<think>` (analyze) → `<plan>` (break down) → `<build>` (execute commands) → `<observe>` (test/verify) → `<sum>` (summarize). Repeat until `<done>true</done>`.
- **Why**: This separates reasoning from action, enables verification, and provides session continuity via plan.md/summary.md persistence.
- **Example**: Each round produces all 5 sections; system processes each section independently.

### Skill-ARCH-2: State Change Markers for Frontend Sync
- **Context**: SSE streaming from Flask to frontend canvas.
- **What**: After each successful state mutation command, yield `__TC_STATE_CHANGED__` marker. Frontend listens for this marker and re-fetches circuit state.
- **Why**: Without explicit markers, the frontend canvas shows stale data. The marker is the only reliable trigger for canvas refresh.
- **Example**: `yield STREAM_STATE_CHANGED_MARKER` after successful `add_element`/`add_wire`/`toggle_input`.

### Skill-ARCH-3: Session Continuity via Persisted Plan/Summary
- **Context**: Multi-round AI agent sessions that may be interrupted.
- **What**: Persist `<plan>` content to `plan.md` and `<sum>` content to `summary.md` after each round. Load both at session start.
- **Why**: Enables recovery from interruption, gives AI full context across rounds, and supports long-running circuit building tasks.
- **Example**: `_atomic_write_md(PLAN_FILE, plan_text)` + `_atomic_write_md(SUMMARY_FILE, sum_text)`.

---

## Frontend

### Skill-FE-1: Cache Busting for Static Files
- **Context**: Flask serves static files without hashing; browser aggressively caches JS/CSS.
- **What**: Add `?v=N` version query parameter to `<script>`/`<link>` tags after every meaningful JS/CSS change. Number up monotonically.
- **Why**: Without cache busting, testers/developers see stale behavior and waste time debugging phantom issues.
- **Example**: `src="/static/scripts/chat.js?v=2"`.

---

## Backend

### Skill-BE-1: Atomic File Writes Prevent Corruption
- **Context**: Writing JSON/markdown state files on any platform.
- **What**: Always write to a temp file first, then `os.replace()` to atomically swap. Clean up stale `.tmp.*` files before writing.
- **Why**: Direct writes risk file corruption on crash or concurrent access. Atomic swap ensures the file is always in a valid state.
- **Example**: `_atomic_write_json()` / `_atomic_write_md()` pattern.

### Skill-BE-2: Streaming Response Context Must Stay Alive
- **Context**: Flask SSE endpoints that execute long-running agent loops.
- **What**: The `request` context and `g` object are NOT available in background threads or streaming generators after the request handler returns. Pass all needed context explicitly as module parameters.
- **Why**: Accessing `request` or `g` inside a generator that yields after the handler exits causes "Working outside of request context" RuntimeError.
- **Example**: Extract `user_message` from `request.json` before entering the generator, pass as parameter.

---

## Circuit Patterns

### CP-Fulladder: Full Adder Circuit Pattern
- **用途**: 全加器 — 三个输入（A, B, CarryIn）相加，输出 SUM 与 CARRY
- **输入**: A, B, CarryIn
- **输出**: SUM, CARRY
- **实现**: 2×HalfAdder + 1×OR（自动检测到 HalfAdder 后会一并注册）
- **构建命令** (~15 条):
  ```
  ADD XOR 240 60 fa_xor1
  ADD AND 240 140 fa_and1
  WIRE $input1 0 fa_xor1 0
  WIRE $input2 0 fa_xor1 1
  WIRE $input1 0 fa_and1 0
  WIRE $input2 0 fa_and1 1
  ADD XOR 400 60 fa_xor2
  ADD AND 400 140 fa_and2
  WIRE fa_xor1 0 fa_xor2 0
  WIRE $input3 0 fa_xor2 1
  WIRE fa_xor1 0 fa_and2 0
  WIRE $input3 0 fa_and2 1
  ADD OR 560 140 fa_or
  WIRE fa_and1 0 fa_or 0
  WIRE fa_and2 0 fa_or 1
  DEFINE_MODULE FullAdder
  ```
- **验证** (8 用例):
  ```
  000→SUM=0,CARRY=0  001→SUM=1,CARRY=0  010→SUM=1,CARRY=0  011→SUM=0,CARRY=1
  100→SUM=1,CARRY=0  101→SUM=0,CARRY=1  110→SUM=0,CARRY=1  111→SUM=1,CARRY=1
  ```
- **复用**: 注册后可用 `ADD MODULE <x> <y> <alias> FullAdder`

### CP-Halfadder: Half Adder Circuit Pattern
- **用途**: 半加器 — 两个输入位相加，输出 SUM（和）与 CARRY（进位）
- **输入**: A, B
- **输出**: SUM, CARRY
- **实现**: 1×XOR + 1×AND
- **构建命令** (~6 条):
  ```
  ADD XOR 240 60 ha_xor
  ADD AND 240 140 ha_and
  WIRE $input1 0 ha_xor 0
  WIRE $input2 0 ha_xor 1
  WIRE $input1 0 ha_and 0
  WIRE $input2 0 ha_and 1
  DEFINE_MODULE HalfAdder
  ```
- **验证** (4 用例):
  ```
  00→SUM=0,CARRY=0  01→SUM=1,CARRY=0  10→SUM=1,CARRY=0  11→SUM=0,CARRY=1
  ```
- **复用**: 注册后可用 `ADD MODULE <x> <y> <alias> HalfAdder`

---

*To add a new skill: when you discover general-purpose knowledge during your work, append it above in this format and increment the total count.*
*To add a new circuit pattern: document the build commands, verify cases, and reusable MODULE name.*
