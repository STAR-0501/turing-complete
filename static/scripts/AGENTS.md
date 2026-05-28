# static/scripts/ — Canvas SPA Frontend

**Purpose:** Browser-side digital logic simulator — editor, simulation, rendering, AI chat UI.  
**Stack:** Vanilla JS (ES modules, Canvas 2D, no frameworks, no bundler)  
**Loaded via:** `<script type="module">` tags in `index.html`

## File Inventory

| File | Lines | Responsibility |
|------|-------|----------------|
| `app.js` | 3128 | Main orchestrator: events, tools (select/drag/wire/delete), undo history, grid snap, camera/zoom, copy/paste, keyboard shortcuts, server I/O (`loadFromServer`, `saveToServer`) |
| `circuit.js` | 376 | Gate evaluation and propagation: `calculateCircuit()`, `getInputSourceState()`, `hasInputConnection()` |
| `renderer.js` | 329 | Canvas drawing: elements (boxes with text labels), wires (colored by signal), signal animation, selection overlays, grid, paste preview |
| `chat.js` | 420 | Agent sidebar UI: SSE streaming, textarea input (`Ctrl+Enter` to send), conversation selector, resize handle, "AI注释"/"AI整理" prompt suggestions |
| `elements.js` | 226 | Element factory functions: `createANDGate()`, `createORGate()`, `createNOTGate()`, `createInputBlock()`, `createOutputBlock()`, `createFunctionBlock()`, `createModuleBlock()` |
| `utils.js` | 42 | Utility functions: `generateId()`, `distance()`, `isPointOnWire()` |

## Module Dependency Graph

```
utils.js ──→ elements.js ──→ app.js ←── chat.js
                ↓               ↓
            circuit.js      renderer.js
```

- `utils.js`: leaf dependency (no imports)
- `elements.js`: imports `generateId` from utils, creates element shapes
- `circuit.js`: leaf (no imports) — pure circuit logic
- `renderer.js`: leaf (no imports) — pure draw logic
- `chat.js`: imports `loadFromServer` from `app.js` (potential circular ref risk)
- `app.js`: imports from utils, elements, circuit, renderer — central hub

## Conventions

- **Naming:** `camelCase` for everything (variables, functions)
- **Exports:** Named `export function` — no default exports
- **Imports:** Named `import { ... }` — explicit import paths with `./` prefix
- **Comments:** Chinese (UTF-8 without BOM); JSDoc `@param`/`@returns` in Chinese
- **State:** Module-level `let` globals in `app.js` (no reactive framework)
- **Constants:** `UPPER_SNAKE_CASE` for const globals (e.g. `GRID_SIZE`, `THINKING_MARKER`)
- **Element IDs:** Generated via `Math.random().toString(36).substr(2, 9)`
- **No type hints:** JS has no type annotations; rely on JSDoc comments
- **No `as any`/`@ts-ignore`:** Type safety enforced by convention
- **No error boundaries:** Canvas operations assume valid state

## Where To Look

| Task | File | Notes |
|------|------|-------|
| Add new element type | `elements.js` | Define geometry, ports, factory function |
| Add rendering for element | `renderer.js` | Switch case in draw loop, text label |
| Change circuit simulation logic | `circuit.js` | `calculateCircuit()`, state propagation |
| Modify canvas interaction | `app.js` | Mouse/pointer events, tool state machine |
| Tweak UI (grid, zoom, camera) | `app.js` | `snapToGrid()`, `camera`, zoom handlers |
| Change wire rendering | `renderer.js` | Wire draw loop, signal colors |
| Modify AI chat sidebar | `chat.js` | SSE handlers, input, conversation list |
| Change prompt suggestions | `chat.js` | `agentPromptSuggestions` array |
| Add/modify undo behavior | `app.js` | `history[]` / `historyIndex` |
| Wire animation toggle | `app.js` | `wireAnimationEnabled`, `btn-wire-anim` |
| Add a utility function | `utils.js` | Shared helpers used across modules |

## Anti-Patterns (This Directory)

- **Circular import risk:** `chat.js` imports `loadFromServer` from `app.js`, while `app.js` sets up globals used by chat — dependency direction is fragile
- **Global state sprawl:** 30+ module-level `let` vars in `app.js` mix editor state, camera state, tool state, and clipboard state
- **Mixed comment language:** Chinese comments with some English — inconsistent
- **No error boundaries:** All canvas operations assume elements/wires arrays are valid; a malformed element causes silent failure
- **History depth:** Undo history stores full state snapshots — no size limit or deduplication
- **Event handler soup:** `app.js` mixes `mousedown`/`mousemove`/`mouseup` for draw, drag, pan, wire, select — state machine is implicit
