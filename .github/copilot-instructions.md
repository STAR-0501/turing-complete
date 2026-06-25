# Turing Complete — Copilot Instructions

This is a **digital logic circuit simulator** (Python Flask 3.1 + Vanilla JS Canvas SPA).

## Entry Points

- **[AGENTS.md](../AGENTS.md)** — Full project knowledge base: architecture, file map, conventions, anti-patterns
- **[CLAUDE.md](../CLAUDE.md)** — Behavioral guidelines for coding LLMs (think before coding, simplicity, surgical changes)

## Submodules

- **[static/scripts/AGENTS.md](../static/scripts/AGENTS.md)** — Frontend Canvas SPA details (ES modules, rendering, circuit engine)
- **[turing_to_arduino/AGENTS.md](../turing_to_arduino/AGENTS.md)** — Circuit-to-Arduino converter

## Key Rules

1. **Simulation logic is duplicated** — `circuit.js` (frontend) AND `ai_commands.py` (backend); always update both
2. **Element templates are duplicated** — `elements.js` AND `ai_commands._get_element_template()`; always update both
3. **No tests exist** — manual verification only; no CI/CD
4. **Dual-format commands** — text AND JSON formats must stay in sync
5. **UTF-8 encoding** — PowerShell: use `[System.IO.File]::WriteAllText`, never `Set-Content`
6. **Terminology** — use 模块 (module) not 函数 (function) for hardware consistency
