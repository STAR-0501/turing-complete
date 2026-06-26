# Turing Complete — Copilot Instructions

This is a **digital logic circuit simulator** (Python Flask 3.1 + Vanilla JS Canvas SPA).

## Entry Points

- **[AGENTS.md](../AGENTS.md)** — Full project knowledge base: architecture, file map, conventions, anti-patterns
- **[CLAUDE.md](../CLAUDE.md)** — Behavioral guidelines for coding LLMs (think before coding, simplicity, surgical changes)

## Submodules

- **[static/scripts/AGENTS.md](../static/scripts/AGENTS.md)** — Frontend Canvas SPA details (ES modules, rendering, circuit engine)
- **[turing_to_arduino/AGENTS.md](../turing_to_arduino/AGENTS.md)** — Circuit-to-Arduino converter

## Built-in Element Types

| Type | Description | Ports |
|------|-------------|-------|
| `AND` / `OR` / `NOT` | 基本逻辑门 | 2 输入 1 输出 / 2 输入 1 输出 / 1 输入 1 输出 |
| `INPUT` / `OUTPUT` | 电路 IO | 0 输入 1 输出 / 1 输入 0 输出 |
| `BYTE_INPUT` | **字节输入器** — 8 位输出 D0-D7 (LSB→MSB)，存储并输出一个字节数值 (0-255)，右键设置值 | 0 输入 + 8 输出 |
| `BYTE_OUTPUT` | **字节显示器** — 8 位输入 D0-D7 (LSB→MSB)，读取各位并显示十进制值 (0-255) | 8 输入 + 0 输出 |
| `FUNCTION` | 自定义模块（由用户封装） | 端口数由内部 INPUT/OUTPUT 数量决定 |

## Key Rules

1. **Simulation logic is duplicated** — `circuit.js` (frontend) AND `ai_commands.py` (backend); always update both
2. **Element templates are duplicated** — `elements.js` AND `ai_commands._get_element_template()`; always update both
3. **No tests exist** — manual verification only; no CI/CD
4. **Dual-format commands** — text AND JSON formats must stay in sync
5. **UTF-8 encoding** — PowerShell: use `[System.IO.File]::WriteAllText`, never `Set-Content`
6. **Terminology** — use 模块 (module) not 函数 (function) for hardware consistency
7. **BYTE elements** — `BYTE_INPUT`: 8 outputs D0-D7, `BYTE_OUTPUT`: 8 inputs D0-D7; port 0 = LSB (weight 1), port 7 = MSB (weight 128); `byteValue` stores the decimal number; `portStates[8]` stores per-bit states
