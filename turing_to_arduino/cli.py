"""turing_to_arduino 包的 CLI 入口点。

支持两种模式：
  1. 仅生成代码（默认）
  2. 完整流水线：生成 + 编译 + 上传（--upload）

用法：
    python -m turing_to_arduino --circuit circuit_data.json
    python -m turing_to_arduino --circuit circuit_data.json --upload --port COM3
    python -m turing_to_arduino --list-ports
"""

import argparse
import json
import sys
from pathlib import Path

from .circuit_parser import parse_circuit
from .code_generator import generate_arduino_sketch
from .uploader import (
    check_arduino_cli,
    compile_sketch,
    detect_boards,
    doctor,
    print_doctor_report,
    upload_sketch,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将 Turing Complete 电路转换为 Arduino 草图"
    )
    parser.add_argument(
        "--circuit",
        type=str,
        default="circuit_data.json",
        help="电路 JSON 文件路径（默认: circuit_data.json）",
    )
    parser.add_argument(
        "--modules",
        type=str,
        default=None,
        help="模块 JSON 文件路径（可选，默认: modules_data.json）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output/sketch",
        help="输出草图目录（默认: ./output/sketch）",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="生成代码后编译并上传",
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="上传目标端口（例如 COM3, /dev/ttyACM0）",
    )
    parser.add_argument(
        "--fqbn",
        type=str,
        default="arduino:avr:uno",
        help="目标板的 FQBN（默认: arduino:avr:uno）",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="运行依赖检查并打印安装指南",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        dest="list_ports",
        help="列出连接的 Arduino 板并退出",
    )

    args = parser.parse_args()

    # ── Mode: doctor ────────────────────────────────────────────────────
    if args.doctor:
        results = doctor()
        print_doctor_report(results)
        has_fail = any(r["status"] == "fail" for r in results)
        sys.exit(1 if has_fail else 0)

    # ── Mode: list ports ──────────────────────────────────────────────
    if args.list_ports:
        try:
            boards = detect_boards()
        except Exception as e:
            print(f"Error detecting boards: {e}", file=sys.stderr)
            sys.exit(1)

        if not boards:
            print("No Arduino boards detected.")
        else:
            for board in boards:
                port = board.get("port", "?")
                name = board.get("name", "?")
                fqbn = board.get("fqbn", "?")
                print(f"{port} - {name} ({fqbn})")
        return

    # ── Mode: code generation ─────────────────────────────────────────
    circuit_path = Path(args.circuit)
    if not circuit_path.is_file():
        print(f"Error: circuit file not found: {circuit_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(circuit_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in circuit file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading circuit file: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Load modules (optional) ───────────────────────────────────────
    modules_data = {}
    modules_path = None
    if args.modules is not None:
        modules_path = Path(args.modules)
    else:
        # 默认模块路径，与电路文件同级
        modules_path = Path("modules_data.json")

    if modules_path and modules_path.is_file():
        try:
            with open(modules_path, "r", encoding="utf-8") as f:
                modules_data = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: could not load modules file: {e}", file=sys.stderr)
            modules_data = {}
    else:
        modules_data = {}

    # ── Parse circuit ─────────────────────────────────────────────────
    try:
        dag = parse_circuit(data, modules_data)
    except Exception as e:
        print(f"Error parsing circuit: {e}", file=sys.stderr)
        sys.exit(1)

    inputs = len(dag.inputs)
    outputs = len(dag.outputs)
    gates = len(dag.gates)
    print(f"Parsed circuit: {inputs} inputs, {outputs} outputs, {gates} gates")

    # ── Generate sketch ───────────────────────────────────────────────
    try:
        sketch_code = generate_arduino_sketch(dag)
    except Exception as e:
        print(f"Error generating sketch: {e}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    sketch_path = output_dir / "sketch.ino"
    try:
        sketch_path.write_text(sketch_code, encoding="utf-8")
    except Exception as e:
        print(f"Error writing sketch file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Sketch written to {output_dir}/sketch.ino")

    # ── Upload mode ───────────────────────────────────────────────────
    if args.upload:
        if not check_arduino_cli():
            from .uploader import _get_arduino_cli_install_guide

            print(
                "Error: arduino-cli not found.\n"
                f"{_get_arduino_cli_install_guide()}\n"
                "Or run:  python -m turing_to_arduino.cli --doctor",
                file=sys.stderr,
            )
            sys.exit(1)

        print("Compiling sketch...")
        ok, out, err = compile_sketch(str(output_dir), args.fqbn)
        if not ok:
            print(f"Compilation failed:\n{err}", file=sys.stderr)
            sys.exit(1)

        if args.port is None:
            print(
                "Error: --port is required for upload (e.g., --port COM3)",
                file=sys.stderr,
            )
            sys.exit(1)

        print("Uploading sketch...")
        ok, out, err = upload_sketch(str(output_dir), args.port, args.fqbn)
        if not ok:
            print(f"Upload failed:\n{err}", file=sys.stderr)
            sys.exit(1)

        print("Upload successful!")


if __name__ == "__main__":
    main()
