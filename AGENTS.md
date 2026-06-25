# Turing Complete — Knowledge Base

**Stack:** Python Flask 3.1 + Vanilla JS (Canvas SPA, ES modules)  
**Purpose:** Digital logic circuit simulator (manual + AI-powered building)  
**No tests, no CI/CD, no Makefile.** PyInstaller spec for distribution.  
**Dependencies:** flask, requests, pyyaml (only 3 packages)

> 📖 **Quick Start** → [README.md](README.md) for running locally  
> 🎯 **AI Protocol** → [AI_INSTRUCTIONS.md](AI_INSTRUCTIONS.md) for command format  
> 🧩 **Frontend** → [static/scripts/AGENTS.md](static/scripts/AGENTS.md) for Canvas SPA details  
> 🔌 **Arduino** → [turing_to_arduino/AGENTS.md](turing_to_arduino/AGENTS.md) for circuit→.ino converter  
> 📐 **Design Docs** → [docs/superpowers/plans/](docs/superpowers/plans/) for implementation plans  
> 📋 **Specs** → [docs/superpowers/specs/](docs/superpowers/specs/) for design specs

## Structure

```
./
├── app.py                  # (~2870L) Flask server: 21 routes, SSE streaming, LLM 5-mode agent loop
├── _common.py              # (110L)  Shared utilities: atomic_write_json/text, AI config, build_api_url
├── ai_commands.py          # (580L)  CircuitManager, simulation engine, command execution
├── agent_config.py         # (132L)  AgentConfig dataclass, YAML config loading
├── instructions.py         # (166L)  InstructionGroup + InstructionManager, %%SCENARIO:xxx%% markers
├── permissions.py          # (60L)   Permission enum, TOOL_PERMISSIONS map, PermissionChecker
├── retry.py                # (70L)   exponential_backoff, retry_call wrapper
├── subagent_manager.py     # (190L)  SubagentManager, semaphore-limited concurrent subagent execution
├── turing_compactor.py     # (105L)  OverflowDetector + ContextCompactor for context management
├── turing_skills.py        # (450L)  Skill + SkillManager, skills/ directory management
├── code_stats.py           # (~40L)  Line count statistics utility
├── templates/
│   └── index.html          # (121L)  Single-page app shell
├── static/
│   ├── scripts/            # (see static/scripts/AGENTS.md)
│   │   ├── app.js          # (~3128L) Canvas editor: events, tools, drag-drop, state, grid snap
│   │   ├── circuit.js      # (~376L)  Element evaluation / propagation
│   │   ├── renderer.js     # (~329L)  Canvas draw: elements (text labels), wires, overlays
│   │   ├── chat.js         # (~420L)  Agent sidebar UI + SSE streaming + textarea input + multi-conversation
│   │   ├── elements.js     # (~226L)  Element type defs & DOM creation
│   │   └── utils.js        # (~42L)   generateId, distance, isPointOnWire
│   └── style/css/
│       └── styles.css      # (~779L)  Cyberpunk-style global stylesheet
├── skills/                 # (13 files) Structured skill .md files (loaded by SkillManager)
├── turing_to_arduino/      # (see turing_to_arduino/AGENTS.md) — standalone Python module
├── docs/
│   └── superpowers/
│       ├── plans/          # Implementation plans (7 files: context, instruction, permission, etc.)
│       └── specs/          # Design specs (2 files: arduino, AI config)
├── agent_config.yaml       # YAML AgentConfig (loaded at startup)
├── ai_config.json          # AI provider config (API key, model, etc.)
├── circuit_data.json       # Persisted circuit state (gitignored)
├── modules_data.json       # Persisted custom module blocks (gitignored)
├── skills.md               # Auto-generated flat index of skills/ directory (read into Agent prompts)
├── plan.md                 # AI plan persistence (5-mode: Think→Plan→Build→Observe→Sum)
├── summary.md              # AI session summary persistence
├── requirements.txt        # flask==3.1.3, requests==2.32.5, pyyaml>=6.0
├── app.spec                # PyInstaller config
├── AI_INSTRUCTIONS.md      # Command protocol for AI agents (text + JSON format)
├── CLAUDE.md               # Behavioral guidelines for coding LLMs
├── README.md               # Project readme
├── ROADMAP.md              # Project roadmap
└── log/                    # AI conversation logs (JSONL, gitignored)
```

## Where To Look

### Backend Core
| Task | File | Notes |
|------|------|-------|
| Add/change backend route | `app.py` | 21 routes: circuit CRUD, AI chat (SSE), config, subagent, Arduino export |
| Change AI agent loop | `app.py`: `call_llm_stream()` / `_build_autonomous_system_prompt()` | 5-mode loop: Think→Plan→Build→Observe→Sum |
| Circuit state management | `ai_commands.py`: `CircuitManager` | Simulation context, command execution, module management |
| Shared utilities | `_common.py` | `atomic_write_json`/`atomic_write_text`, `get_ai_config`, `build_api_url` |
| Command protocol | `AI_INSTRUCTIONS.md` | Text & JSON dual-format command specs |
| Schema config | `agent_config.py` + `agent_config.yaml` | `AgentConfig` dataclass, YAML loading at startup |
| AI provider config | `_common.py` + `ai_config.json` | JSON config with DeepSeek defaults; unified via `get_ai_config()` |
| Context compaction | `turing_compactor.py` + `app.py` | OverflowDetector → ContextCompactor; keeps last 2 rounds |
| Permission system | `permissions.py` + `app.py` `execute_circuit_command()` | READ/EXEC/WRITE/ADMIN levels, `PermissionChecker.check_tool()` gate |
| Subagent system | `subagent_manager.py` + `app.py` `/api/subagent` | Semaphore-limited (max 3) concurrent LLM calls; SPAWN/CHECK/WAIT commands |
| Skill system | `turing_skills.py` + `skills/` + `skills.md` | SkillManager scans `skills/*.md`; auto-generates `skills.md` index |
| Instruction scenarios | `instructions.py` + `AI_INSTRUCTIONS.md` | `%%SCENARIO:always/test/debug/module/optimize%%` markers; priority 100→50 |
| Retry & backoff | `retry.py` + `app.py` `_call_llm_once/streaming` | 3 retries, exponential backoff (1s→30s), jitter, on 429/5xx |
| Circuit pattern detection | `app.py`: `_detect_circuit_pattern()` / `KNOWN_CIRCUIT_PATTERNS` | AI done=true → topology match → auto DEFINE_MODULE |
| AI plan/summary | `app.py`: `PLAN_FILE` / `SUMMARY_FILE` | Atomic writes to `plan.md` / `summary.md` for session continuity |
| Conversation logging | `app.py`: `_log_conversation()` | JSONL logs in `log/` (gitignored) |
| Arduino export | `turing_to_arduino/` (standalone) + `app.py` `/api/export-arduino` | Circuit→Arduino `.ino` conversion + optional `arduino-cli` upload |
| Design docs | `docs/superpowers/plans/` + `docs/superpowers/specs/` | Implementation plans (7) and design specs (2) for all mechanisms |

### Frontend
| Task | File | Notes |
|------|------|-------|
| Add new element type | `static/scripts/elements.js` + `ai_commands.py` | Frontend factory + backend template — MUST update both (known duplication) |
| Change rendering | `static/scripts/renderer.js` | Canvas draw: boxes with text labels, signal-colored wires |
| Modify simulation | `static/scripts/circuit.js` | Gate evaluation, state propagation (mirrored in `ai_commands.py`) |
| Canvas editor behavior | `static/scripts/app.js` | Events, tools, drag-drop, undo history, grid snap (20px), camera/zoom, keyboard shortcuts |
| Agent sidebar / chat UI | `static/scripts/chat.js` | SSE streaming, textarea (Ctrl+Enter send), conversation selector, resize handle, prompt suggestions |
| CSS / styling | `static/style/css/styles.css` | Cyberpunk theme, Chinese comments |
| Wire animation | `app.js`: `wireAnimationEnabled` / `btn-wire-anim` | Toolbar toggle for signal propagation animation |
| Grid snapping | `app.js`: `snapToGrid()` / `syncGridToCamera()` | 20px snap, always active, syncs with camera |
| Element labels | `renderer.js`: switch cases | AND/OR/NOT/IN/OUT text labels centered in element box |
| Agent textarea | `chat.js`: `keydown` handler | Multi-line, Enter=newline, Ctrl+Enter=send, auto-height |
| Sidebar resize | `chat.js`: resize handle + `styles.css` | Left-edge drag handle, 280–600px range |
| Round markers | `chat.js`: `ROUND_MARKER` | `__TC_ROUND__` creates per-round message divs |
| SSE session tracking | `chat.js` + `app.py` `generate()` | `__TC_SESSION__:{id}` first SSE line; `__TC_STATE_CHANGED__` triggers canvas reload |

## Conventions

- **Language:** Python 3 + Vanilla JS (no frameworks, no bundler)
- **Naming — Python:** `snake_case` functions, `PascalCase` classes
- **Naming — JS:** `camelCase` for everything; `UPPER_SNAKE_CASE` for constants
- **Terminology:** 模块 (module) not 函数 (function) — consistent with hardware standard
- **Dual-format commands:** text (`ADD AND 240 200`) AND JSON (`{"tool":"add_element","params":{...}}`) both supported
- **HTML loaded as `<script type="module">` tags** (ES modules, no bundler)
- **Frontend global state:** module-level `let` vars in `app.js` (no reactive framework)
- **No type hints in JS;** JSDoc `@param`/`@returns` in Chinese for documentation
- **Flask routes** return `jsonify()` for API, `render_template()` for page
- **AI config** dual-source: `ai_config.json` (JSON, `_AI_CONFIG_DEFAULTS` fallback) + `agent_config.yaml` (YAML, `AgentConfig`); unified via `_common.get_ai_config()`
- **Data persistence** via atomic JSON writes (`atomic_write_json` in `_common.py`)
- **SSE streaming** for AI responses (`text/event-stream`)
- **CSS** in Chinese comments; single stylesheet (`styles.css`, ~779L)
- **No ORM, no database** — flat JSON file storage
- **UTF-8 policy:** All source files without BOM; PowerShell write via `[System.IO.File]::WriteAllText` with explicit UTF8

## Anti-Patterns (This Project)

- **AI config redundancy** — `ai_config.json` + `agent_config.yaml` coexist with overlapping model settings; `_common.py` provides unified access but both files still exist
- **Frontend-backend duplication (element templates)** — `ai_commands.py` `_get_element_template()` and `elements.js` `create*()` define identical geometries; changing one **requires** updating the other
- **Frontend-backend duplication (simulation)** — `circuit.js` (client-side) and `ai_commands.py` (server-side) implement identical gate logic; both needed but must be kept in sync
- **Frontend coupling** — `chat.js` imports from `app.js` (potential circular ref risk)
- **Mixed comment languages** — Chinese + English in same files, inconsistent
- **No error boundaries** in JS — canvas operations assume valid state
- **PowerShell encoding pitfall** — `Set-Content` defaults to Windows-1252, corrupts UTF-8 Chinese text; use `[System.IO.File]::WriteAllText` with explicit UTF8
- **`turing_to_arduino/` uses `print()`** instead of `logging` for debug output
- **`retry.py`** has a dead `def wrapper(...)` at the end (incomplete decorator attempt)

## Commands

```bash
pip install -r requirements.txt   # install deps
# NOTE: `python app.py` does NOT stop on its own once started.
#       Do NOT start the server yourself or force-kill it mid-session.
# python app.py                   # dev server (http://localhost:5000)
python code_stats.py             # line count statistics
# No test/build/CI commands exist
```

## Notes

- `_quick_classify()` branches into **circuit mode** (agent loop) or **chat mode** (freeform)
- Agent uses 5-mode tags: `<think>`, `<plan>`, `<build>`, `<observe>`, `<sum>`, `<answer>`, `<done>`
- **Circuit pattern auto-detection:** AI declares `done=true` → `_detect_circuit_pattern()` matches topology against `KNOWN_CIRCUIT_PATTERNS` (HalfAdder, FullAdder) → `_auto_register_circuit_patterns()` writes to modules_data.json and skills.md
- Supports dual-format commands: traditional text AND JSON (parsed more stably)
- Dual format also applies to *diff feedback* from verify steps
- Frontend `history[]`/`historyIndex` for undo (limited depth)
- `.sisyphus/` and `.trae/` are tool config dirs — not project code
- `log/` stores JSONL conversation logs; gitignored — safe to delete for reset
- `plan.md` and `summary.md` provide session continuity across restarts
- `__TC_ROUND__` markers create separate message divs per round in the chat UI
- `__TC_STATE_CHANGED__` triggers canvas reload when circuit state changes
- `__TC_SESSION__:{id}` sent as first line of SSE stream; frontend uses it to track current conversation session
- Streaming command executor (`_feed_stream_commands`) executes build commands in real-time during LLM output; post-hoc extraction serves as fallback
- Agent input is a `<textarea>` with auto-height; send via `Ctrl+Enter`, newline via `Enter`
- Prompt suggestion buttons ("AI注释"/"AI整理") appear above input when empty, fill predefined text on click
- "深度思考" toggle enables AI reasoning mode (`reasoning_effort: high`)
- Grid snap (20px) is always active; grid visual syncs with camera via `syncGridToCamera()`
- Element rendering uses text labels (AND/OR/NOT/IN/OUT) centered in the element box
- **Context compaction** runs at end of each agent round: `OverflowDetector` checks token estimate → `ContextCompactor` summarizes older rounds while preserving last 2
- **Permission system** gates all `execute_circuit_command()` calls: READ/WRITE/ADMIN levels, checked via `PermissionChecker.check_tool()`
- **Subagent system** spawns concurrent LLM calls with `SubagentManager` (semaphore-limited), polled via `CHECK_SUBAGENT`/`WAIT_SUBAGENT` commands
- **Retry mechanism** wraps `_call_llm_once` and `_call_llm_streaming` with exponential backoff (3 retries, max 32s interval)
- **Skill system** uses `SkillManager` to load structured skills from `skills/` directory; `skills.md` is auto-generated flat index for prompt injection
- **Instruction scenarios** use `%%SCENARIO:xxx%%` markers in `AI_INSTRUCTIONS.md` — 5 groups: always, test, debug, module, optimize
- **Schema config** loaded via `AgentConfig.from_yaml()` at startup from `agent_config.yaml`
