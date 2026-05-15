# Turing Complete — Knowledge Base

**Stack:** Python Flask 3.1 + Vanilla JS (Canvas-based SPA)  
**Purpose:** Digital logic circuit simulator (manual + AI-powered building)  
**No tests, no CI/CD, no Makefile.** PyInstaller spec for distribution.

## Structure

```
./
├── app.py                  # Flask server: routes, SSE streaming, LLM agent loop (5-mode)
├── ai_commands.py          # CircuitManager, simulation engine, command execution
├── templates/
│   └── index.html          # (98L)   Single-page app shell
├── static/
│   ├── scripts/
│   │   ├── app.js          # (2652L) Canvas editor: events, tools, drag-drop, state, grid snap
│   │   ├── circuit.js      # (334L)  Element evaluation / propagation
│   │   ├── renderer.js     # (279L)  Canvas draw: elements (text labels), wires, overlays
│   │   ├── chat.js         # (298L)  Agent sidebar UI + SSE streaming + textarea input + multi-conversation
│   │   ├── elements.js     # (212L)  Element type defs & DOM creation
│   │   └── utils.js        # (36L)   generateId, distance, isPointOnWire
│   └── style/css/
│       └── styles.css      # (779L)
├── circuit_data.json       # Persisted circuit state
├── modules_data.json       # Persisted custom module blocks
├── skills.md               # Self-evolving skills base (agent-extracted skills)
├── plan.md                 # AI plan persistence (5-mode: Think→Plan→Build→Observe→Sum)
├── summary.md              # AI session summary persistence
├── requirements.txt        # flask, requests
├── app.spec                # PyInstaller config
├── AI_INSTRUCTIONS.md      # Command protocol for AI agents
├── CLAUDE.md               # Behavioral guidelines for coding LLMs
├── agenda.md               # Scratchpad / TODO
├── 重构计划.md              # Chinese refactoring plan (app.py modularization)
└── log/                    # AI conversation logs (JSONL, gitignored)
```

## Where To Look

| Task | File | Notes |
|------|------|-------|
| Add a new element type | `static/scripts/elements.js` | Define ports, labels, draw geometry |
| Change rendering | `static/scripts/renderer.js` | Canvas draw logic |
| Modify circuit simulation | `static/scripts/circuit.js` | Gate evaluation, state propagation |
| Add backend route | `app.py` | Flask routes in `@app.route` blocks |
| Change AI agent loop | `app.py`: `call_llm_stream` / `_build_autonomous_system_prompt` | Multi-round Plan→Execute→Check |
| Circuit state management | `ai_commands.py`: `CircuitManager` | Simulation context, commands |
| Command protocol | `AI_INSTRUCTIONS.md` | Text & JSON formats for AI tools |
| Add/change module blocks | `ai_commands.py` + frontend `elements.js` | Both sides need updates |
| Change AI 5-mode loop | `app.py`: `call_llm_stream` / `_build_autonomous_system_prompt` | Think→Plan→Build→Observe→Sum |
| AI plan/summary persistence | `app.py`: `PLAN_FILE` / `SUMMARY_FILE` | Atomic markdown writes to plan.md/summary.md |
| AI self-evolution / skills system | `app.py`: `SKILLS_FILE` / `_merge_skills()` / `skills.md` | Agent `<skills>` block → extracted, deduped, persisted to skills.md |
| Circuit pattern auto-detection | `app.py`: `_detect_circuit_pattern()` / `KNOWN_CIRCUIT_PATTERNS` | AI declares done=true → match topology → auto DEFINE_MODULE |
| Streaming command execution | `app.py`: `_feed_stream_commands` | Real-time build execution during LLM streaming |
| Conversation logging | `app.py`: `_log_conversation` | JSONL logs in `log/` (gitignored) |
| Frontend round markers | `chat.js`: `ROUND_MARKER` | `__TC_ROUND__` markers create per-round message divs |
| Agent sidebar / chat | `chat.js` + `static/style/css/styles.css` | Collapsible right sidebar, SSE streaming, thinking split, prompt suggestions |
| Wire animation toggle | `app.js`: `wireAnimationEnabled` / `btn-wire-anim` | Toolbar button to toggle signal propagation animation |
| Grid snapping | `app.js`: `snapToGrid()` / `syncGridToCamera()` | 20px snap aligned to background grid; `GRID_SIZE` constant |
| Element labels | `renderer.js`: switch cases | AND/OR/NOT/IN/OUT text labels (no graphic symbols) |
| Agent prompt suggestions | `chat.js`: `agentPromptSuggestions` / `index.html` | "AI注释"/"AI整理" buttons above textarea when empty |
| Agent textarea input | `chat.js`: `keydown` handler | Multi-line textarea, Ctrl+Enter to send, Enter for newline |
| Agent sidebar resize | `chat.js`: resize handle + `styles.css` | Left-edge drag handle to adjust width (280–600px) |
| Conversation history API | `app.py`: `list_conversations()` / `get_conversation()` | `GET /api/conversations` 列表 + `GET /api/conversations/<id>` 消息 |
| Conversation selector UI | `chat.js`: `loadConversationList()` / `loadConversationMessages()` + `index.html` | Agent header 下拉框切换 log/ 目录下的历史对话 |
| SSE session marker | `app.py`: `/api/chat` `generate()` | 流首行 `__TC_SESSION__:{id}` 标记，前端自动追踪当前会话 |

## Conventions

- **Language:** Python 3 + Vanilla JS (no frameworks, no bundler)
- **Naming — Python:** `snake_case` functions, `PascalCase` classes
- **Naming — JS:** `camelCase` for everything
- **Terminology:** 模块 (module) not 函数 (function) — consistent with hardware standard
- **Dual-format commands:** text (`ADD AND 240 200`) AND JSON (`{"cmd":"ADD","type":"AND"}`) both supported
- **HTML loaded as `<script>` tags** (no ES modules, no bundler)
- **Frontend global state:** module-level `let` vars in `app.js`
- **No type hints in JS;** Python uses minimal type hints
- **Flask routes** return `jsonify()` for API, `render_template()` for page
- **AI config** hardcoded in `app.py` `AI_CONFIG` dict (DeepSeek API)
- **Data persistence** via atomic JSON writes (`_atomic_write_json`)
- **SSE streaming** for AI responses (`text/event-stream`)
- **CSS** in Chinese comments; single stylesheet
- **No ORM, no database** — flat JSON file storage
- **UTF-8 policy:** All source files without BOM; PowerShell write via `[System.IO.File]::WriteAllText` with explicit UTF8 encoding

## Anti-Patterns (This Project)

- **Duplicated `_atomic_write_json`** (`app.py` and `ai_commands.py` both define it)
- **Duplicated `build_io_summary`-like logic** across backend files
- **API key hardcoded** in `app.py` `AI_CONFIG` (committed to git)
- **Frontend coupling:** `app.js` imports from `chat.js` at module level (potential circular refs)
- **Mixed comment languages** (Chinese + English in same files, inconsistent)
- **No error boundaries** in JS — canvas operations assume valid state
- **PowerShell encoding pitfall:** `Set-Content` defaults to system ANSI (Windows-1252) — corrupts UTF-8 Chinese text; use `WriteAllText` with explicit UTF8
- **No `as any`/`@ts-ignore`/`@ts-expect-error`** in JS — type safety enforced by convention

## Commands

```bash
pip install -r requirements.txt   # install deps
# NOTE: `python app.py` does NOT stop on its own once started.
#       Do NOT start the server yourself or force-kill it mid-session.
# python app.py                   # dev server (http://localhost:5000)
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
- Agent input is a `<textarea>` with auto-height; send via `Ctrl+Enter`, newline via `Enter`
- Prompt suggestion buttons ("AI注释"/"AI整理") appear above input when empty, fill predefined text on click
- "深度思考" toggle enables AI reasoning mode (`reasoning_effort: high`)
- Grid snap (20px) is always active; grid visual syncs with camera via `syncGridToCamera()`
- Element rendering uses text labels (AND/OR/NOT/IN/OUT) centered in the element box
