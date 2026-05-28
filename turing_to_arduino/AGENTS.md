# turing_to_arduino/ — Circuit-to-Arduino Converter

**Purpose:** Convert Turing Complete's `circuit_data.json` into Arduino `.ino` sketches, with optional compilation and upload via `arduino-cli`.  
**Stack:** Python 3 (stdlib only — json, subprocess, argparse, dataclasses)  
**Status:** Standalone package (not imported by `app.py`). Can run independently via `python -m turing_to_arduino`.

## File Inventory

| File | Lines | Responsibility |
|------|-------|----------------|
| `__init__.py` | 23 | Public API: re-exports `CircuitDAG`, `CircuitNode`, `parse_circuit`, `generate_arduino_sketch`, upload/doctor functions |
| `circuit_parser.py` | 332 | Parse `circuit_data.json` → `CircuitDAG` with topological sort. Handles FUNCTION module expansion, auto pin mapping, feedback loop detection |
| `code_generator.py` | 113 | Convert `CircuitDAG` → Arduino `.ino` string. Signal-flow variable approach: `digitalRead` → bool gates → `digitalWrite` |
| `cli.py` | 250 | `argparse` CLI: `--circuit`, `--upload`, `--port`, `--fqbn`, `--doctor`, `--list-ports`. Entry: `main()` |
| `uploader.py` | 312 | `arduino-cli` wrapper: `compile_sketch()`, `detect_boards()`, `upload_sketch()`, `doctor()`. Platform-specific install guides |

## Architecture / Data Flow

```
circuit_data.json + modules_data.json
           ↓
circuit_parser.py : parse_circuit()
           ↓
     CircuitDAG (inputs, outputs, gates, pin_map)
           ↓
code_generator.py : generate_arduino_sketch()
           ↓
     sketch.ino (text)
           ↓
uploader.py : compile_sketch() → upload_sketch() [optional]
```

- **CLI mode:** `cli.py:main()` — standalone entry via `python -m turing_to_arduino`
- **Library mode:** Import `parse_circuit` + `generate_arduino_sketch` from the package

## Conventions

- **Naming:** `snake_case` functions, `PascalCase` classes. Constants: `UPPER_SNAKE_CASE`
- **Type hints:** Annotated (stdlib `typing`, `from __future__ import annotations` in parser)
- **Dataclasses:** `@dataclass` for `CircuitNode`, `CircuitDAG` in `circuit_parser.py`
- **No external deps:** Python stdlib only (json, subprocess, argparse, collections.deque, dataclasses, shutil)
- **Docstrings:** Module-level docstrings (triple-quoted), function docstrings with Args/Returns sections
- **Error handling:** Early return on check failure; `sys.exit(1)` on doctor failure
- **CLI defaults:** `--circuit` defaults to `circuit_data.json`, `--fqbn` defaults to `arduino:avr:uno`
- **Platform awareness:** Upload paths differ for win32/darwin/linux in doctor install guides

## Where To Look

| Task | File | Notes |
|------|------|-------|
| Change circuit JSON parsing | `circuit_parser.py` | `_parse_wire_endpoint()`, `_build_dag()` |
| Add new element type support | `circuit_parser.py` | `_is_gate()` / `_expand_function()` |
| Modify generated Arduino code | `code_generator.py` | `generate_arduino_sketch()` template |
| Change pin mapping logic | `circuit_parser.py` | `auto_pin_map` generation |
| Add a CLI flag | `cli.py` | `argparse.ArgumentParser.add_argument()` |
| Fix upload/compile behavior | `uploader.py` | Subprocess call wrappers |
| Update dependency check | `uploader.py` | `doctor()` function |
| Use as a library | `__init__.py` + any source | Import `parse_circuit`, `generate_arduino_sketch` |

## Anti-Patterns (This Directory)

- **No automated tests:** No test files or test runner configured
- **Mixed import styles:** `code_generator.py` uses `Dict` from typing; other files use `dict[str, Any]` style
- **Hardcoded defaults:** Pin map generation uses hardcoded starting pin (usually 2) — not configurable
- **No logging:** Uses `print()` for output instead of `logging` module
- **Error visibility:** Subprocess errors in `uploader.py` are captured but may be opaque to users
- **No progress indication:** Compile/upload operations can be slow with no feedback
