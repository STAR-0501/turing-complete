# Turing Complete — Knowledge Base

**Stack:** Python Flask 3.1 + Vanilla JS (Canvas-based SPA)  
**Purpose:** Digital logic circuit simulator (manual + AI-powered building)  
**No tests, no CI/CD, no Makefile.** PyInstaller spec for distribution.

## Structure

```
./
├── app.py                  # Flask server: routes, SSE streaming, LLM agent loop
├── ai_commands.py          # CircuitManager, simulation engine, command execution
├── templates/
│   └── index.html          # Single-page app shell
├── static/
│   ├── scripts/
│   │   ├── app.js          # (2765L) Canvas editor: events, tools, drag-drop, state
│   │   ├── circuit.js      # (331L)  Element evaluation / propagation
│   │   ├── renderer.js     # (377L)  Canvas draw: elements, wires, overlays
│   │   ├── chat.js         # (210L)  Chat UI + SSE streaming display
│   │   ├── elements.js     # (220L)  Element type defs & DOM creation
│   │   └── utils.js        # (39L)   generateId, distance, isPointOnWire
│   └── style/css/
│       └── styles.css      # (456L)
├── circuit_data.json       # Persisted circuit state
├── functions_data.json     # Persisted custom function blocks
├── requirements.txt        # flask, requests
├── app.spec                # PyInstaller config
├── AI_INSTRUCTIONS.md      # Command protocol for AI agents
├── CLAUDE.md               # Behavioral guidelines for coding LLMs
└── agenda.md               # Scratchpad / TODO
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
| Add/change function blocks | `ai_commands.py` + frontend `elements.js` | Both sides need updates |

## Conventions

- **Language:** Python 3 + Vanilla JS (no frameworks, no bundler)
- **Naming — Python:** `snake_case` functions, `PascalCase` classes
- **Naming — JS:** `camelCase` for everything
- **HTML loaded as `<script>` tags** (no ES modules, no bundler)
- **Frontend global state:** module-level `let` vars in `app.js`
- **No type hints in JS;** Python uses minimal type hints
- **Flask routes** return `jsonify()` for API, `render_template()` for page
- **AI config** hardcoded in `app.py` `AI_CONFIG` dict (DeepSeek API)
- **Data persistence** via atomic JSON writes (`_atomic_write_json`)
- **SSE streaming** for AI responses (`text/event-stream`)
- **CSS** in Chinese comments; single stylesheet
- **No ORM, no database** — flat JSON file storage

## Anti-Patterns (This Project)

- **Duplicated `_atomic_write_json`** (`app.py` and `ai_commands.py` both define it)
- **Duplicated `build_io_summary`-like logic** across backend files
- **API key hardcoded** in `app.py` `AI_CONFIG` (committed to git)
- **Frontend coupling:** `app.js` imports from `chat.js` at module level (potential circular refs)
- **Mixed comment languages** (Chinese + English in same files, inconsistent)
- **No error boundaries** in JS — canvas operations assume valid state

## Commands

```bash
pip install -r requirements.txt   # install deps
python app.py                      # dev server (http://localhost:5000)
# No test/build/CI commands exist
```

## Notes

- `_quick_classify()` branches into **circuit mode** (agent loop) or **chat mode** (freeform)
- Agent uses tags: `<plan>`, `<commands>`, `<verify>`, `<done>`, `<think>`, `<answer>`
- Supports dual-format commands: traditional text AND JSON (parsed more stably)
- Dual format also applies to *diff feedback* from verify steps
- Frontend `history[]`/`historyIndex` for undo (limited depth)
- `.sisyphus/` and `.trae/` are tool config dirs — not project code
