"""arduino-cli CLI wrapper for compile, board detection, and upload operations."""

import json
import shutil
import subprocess
import sys
from typing import Any

__all__ = [
    "check_arduino_cli",
    "compile_sketch",
    "detect_boards",
    "upload_sketch",
    "doctor",
]

ARDUINO_CLI = "arduino-cli"

# ── Dependency check / doctor ───────────────────────────────────────────


def _get_arduino_cli_install_guide() -> str:
    """Return platform-specific arduino-cli install instructions."""
    if sys.platform == "win32":
        return (
            "  Windows:\n"
            "    1. Download Arduino CLI from:\n"
            "       https://arduino.github.io/arduino-cli/1.2/installation/\n"
            "    2. Extract arduino-cli.exe to a folder (e.g. C:\\arduino-cli)\n"
            "    3. Add that folder to your system PATH\n"
            "    4. Restart your terminal\n"
            "    5. Run:  arduino-cli core install arduino:avr\n"
            "  Or install via Scoop:  scoop install arduino-cli\n"
        )
    elif sys.platform == "darwin":
        return (
            "  macOS:\n"
            "    brew install arduino-cli\n"
            "    arduino-cli core install arduino:avr\n"
        )
    else:
        return (
            "  Linux:\n"
            "    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh\n"
            "    arduino-cli core install arduino:avr\n"
        )


def _get_arduino_core_install_guide() -> str:
    """Return instructions to install Arduino AVR core."""
    return (
        "  Run:  arduino-cli core install arduino:avr\n"
        "  This installs the toolchain for Arduino Uno.\n"
    )


def doctor() -> list[dict[str, Any]]:
    """Run comprehensive dependency checks.

    Returns:
        A list of check results, each a dict with keys:
          - name: check name
          - status: \"pass\" / \"fail\" / \"warn\"
          - message: human-readable description
    """
    results: list[dict[str, Any]] = []

    # Check 1: arduino-cli binary
    cli_path = shutil.which(ARDUINO_CLI)
    if cli_path:
        results.append({
            "name": "arduino-cli binary",
            "status": "pass",
            "message": f"Found at: {cli_path}",
        })
    else:
        results.append({
            "name": "arduino-cli binary",
            "status": "fail",
            "message": f"Not found in PATH.\n{_get_arduino_cli_install_guide()}",
        })
        return results  # can't check further without arduino-cli

    # Check 2: arduino:avr core
    try:
        result = subprocess.run(
            [ARDUINO_CLI, "core", "list", "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            cores = _normalize_platform_list(json.loads(result.stdout))
            avr_installed = any(
                c.get("id") == "arduino:avr" for c in cores
            )
            if avr_installed:
                results.append({
                    "name": "arduino:avr core",
                    "status": "pass",
                    "message": "Arduino AVR core is installed.",
                })
            else:
                results.append({
                    "name": "arduino:avr core",
                    "status": "fail",
                    "message": (
                        "arduino:avr core not found.\n"
                        f"{_get_arduino_core_install_guide()}"
                    ),
                })
        else:
            results.append({
                "name": "arduino:avr core",
                "status": "warn",
                "message": (
                    f"Could not list cores (exit {result.returncode}).\n"
                    "Run manually: arduino-cli core list\n"
                ),
            })
    except Exception as e:
        results.append({
            "name": "arduino:avr core",
            "status": "warn",
            "message": f"Error checking cores: {e}",
        })

    # Check 3: connected boards
    try:
        board_result = subprocess.run(
            [ARDUINO_CLI, "board", "list", "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if board_result.returncode == 0:
            boards = _normalize_board_list(json.loads(board_result.stdout))
            if boards:
                for b in boards:
                    results.append({
                        "name": f"Board on {b['address']}",
                        "status": "pass",
                        "message": f"{b['name']} ({b['fqbn']})",
                    })
            else:
                results.append({
                    "name": "Connected boards",
                    "status": "warn",
                    "message": (
                        "No boards detected. Connect your Arduino via USB.\n"
                        "  Windows: Check Device Manager for COM port.\n"
                        "  Linux:   Check lsusb / dmesg.\n"
                        "  macOS:   Check /dev/tty.*\n"
                    ),
                })
        else:
            results.append({
                "name": "Connected boards",
                "status": "warn",
                "message": "Could not list boards (arduino-cli error).",
            })
    except Exception as e:
        results.append({
            "name": "Connected boards",
            "status": "warn",
            "message": f"Error listing boards: {e}",
        })

    return results


def print_doctor_report(results: list[dict[str, Any]]) -> None:
    """Print a formatted doctor report to stdout."""
    status_icons = {"pass": "[OK]", "fail": "[FAIL]", "warn": "[WARN]"}
    all_pass = all(r["status"] == "pass" for r in results)
    print()
    print("=" * 56)
    print("  turing_to_arduino - Dependency Check Report")
    print("=" * 56)
    for r in results:
        icon = status_icons.get(r["status"], " ")
        print(f"\n  {icon}  {r['name']}")
        for line in r["message"].split("\n"):
            print(f"     {line}")
    print()
    print("-" * 56)
    if all_pass:
        print("  [OK] All checks passed. Ready to compile and upload.")
    else:
        failed = [r["name"] for r in results if r["status"] == "fail"]
        if failed:
            print(f"  [FAIL] {len(failed)} check(s) failed: {', '.join(failed)}")
        print("  Follow the instructions above to resolve issues.")
    print("=" * 56)
    print()


def check_arduino_cli() -> bool:
    """Check if arduino-cli is installed and in PATH."""
    return shutil.which(ARDUINO_CLI) is not None


def compile_sketch(
    sketch_dir: str, fqbn: str = "arduino:avr:uno"
) -> tuple[bool, str, str]:
    """Compile an Arduino sketch.

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully qualified board name (default: arduino:avr:uno).

    Returns:
        Tuple of (success, stdout, stderr).
    """
    if not check_arduino_cli():
        return (False, "", "arduino-cli not found")

    cmd = [ARDUINO_CLI, "compile", "--fqbn", fqbn, sketch_dir]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        success = result.returncode == 0
        return (success, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "compile timed out")
    except FileNotFoundError:
        return (False, "", "arduino-cli not found")


def _normalize_board_list(data: Any) -> list[dict[str, Any]]:
    """Normalize arduino-cli board list JSON (supports 1.5+ and legacy formats).

    arduino-cli 1.5+:  {"detected_ports": [{"port": {...}, "matching_boards": [...]}]}
    Legacy format:     [{"port": {...}, "name": "...", "fqbn": "..."}]

    Returns:
        A list of dicts, each with keys: address, label, name, fqbn.
    """
    if isinstance(data, list):
        # Legacy format — normalize to same flat structure
        result: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            port_info = entry.get("port", {})
            address = port_info.get("address", "?") if isinstance(port_info, dict) else "?"
            label = port_info.get("label", address) if isinstance(port_info, dict) else address
            result.append({
                "address": address,
                "label": label,
                "name": entry.get("name", "Unknown board"),
                "fqbn": entry.get("fqbn", "?"),
            })
        return result

    if isinstance(data, dict):
        ports = data.get("detected_ports", [])
        if not isinstance(ports, list):
            return []

        result: list[dict[str, Any]] = []
        for entry in ports:
            port_info = entry.get("port", {}) if isinstance(entry, dict) else {}
            address = port_info.get("address", "?") if isinstance(port_info, dict) else "?"
            label = port_info.get("label", address) if isinstance(port_info, dict) else address

            matching = entry.get("matching_boards", []) if isinstance(entry, dict) else []
            if isinstance(matching, list) and matching:
                for mb in matching:
                    if isinstance(mb, dict):
                        result.append({
                            "address": address,
                            "label": label,
                            "name": mb.get("name", "Unknown board"),
                            "fqbn": mb.get("fqbn", "?"),
                        })
            else:
                result.append({
                    "address": address,
                    "label": label,
                    "name": "Unknown board",
                    "fqbn": "?",
                })
        return result

    return []


def _normalize_platform_list(data: Any) -> list[dict[str, Any]]:
    """Normalize arduino-cli core list JSON (supports 1.5+ and legacy formats).

    arduino-cli 1.5+:  {"platforms": [...]}
    Legacy format:     [...]

    Returns:
        A list of platform dicts.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("platforms", [])
    return []


def detect_boards() -> list[dict[str, Any]]:
    """Detect connected Arduino boards.

    Returns:
        List of board info dictionaries. Empty list on failure.
        Each dict has keys: address, label, name, fqbn.
    """
    if not check_arduino_cli():
        return []

    cmd = [ARDUINO_CLI, "board", "list", "--format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        return _normalize_board_list(data)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
        return []


def upload_sketch(
    sketch_dir: str, port: str, fqbn: str = "arduino:avr:uno"
) -> tuple[bool, str, str]:
    """Upload a compiled sketch to an Arduino board.

    Args:
        sketch_dir: Path to the sketch directory.
        port: Serial port (e.g., COM3 or /dev/ttyACM0).
        fqbn: Fully qualified board name (default: arduino:avr:uno).

    Returns:
        Tuple of (success, stdout, stderr).
    """
    if not check_arduino_cli():
        return (False, "", "arduino-cli not found")

    cmd = [ARDUINO_CLI, "upload", "--fqbn", fqbn, "--port", port, sketch_dir]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        success = result.returncode == 0
        return (success, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "upload timed out")
    except FileNotFoundError:
        return (False, "", "arduino-cli not found")
