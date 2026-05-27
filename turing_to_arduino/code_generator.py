from typing import Dict
from .circuit_parser import CircuitDAG, CircuitNode


def _safe_name(alias: str) -> str:
    """Convert an alias to a valid Arduino C variable name.

    Replaces non-alphanumeric, non-underscore characters with '_'.
    Prepends '_' if the name starts with a digit.
    Lowercases the result per Arduino C++ convention.
    """
    chars = []
    for c in alias:
        if c.isalnum() or c == '_':
            chars.append(c)
        else:
            chars.append('_')
    name = ''.join(chars)
    if name and name[0].isdigit():
        name = '_' + name
    return name.lower()


def _resolve_var(node_id: str, var_map: Dict[str, str]) -> str:
    """Look up the variable name for a given node ID.

    Args:
        node_id: The CircuitNode.id to resolve.
        var_map: Mapping of node_id -> Arduino variable name.

    Returns:
        The variable name, or a C comment placeholder if unknown.
    """
    if node_id in var_map:
        return var_map[node_id]
    return f"/* unknown: {node_id} */"


def generate_arduino_sketch(dag: CircuitDAG) -> str:
    """Convert a CircuitDAG into an Arduino .ino sketch string.

    The generated sketch uses the signal-flow variable approach:
    - INPUT nodes are read via digitalRead into bool variables.
    - Gates (AND/OR/NOT/FUNCTION) are evaluated in topological order,
      each into a sequentially-numbered bool (t1, t2, ...).
    - OUTPUT nodes write their source variable via digitalWrite.

    Args:
        dag: A topologically-sorted CircuitDAG from circuit_parser.

    Returns:
        A complete Arduino .ino file as a single string.
    """
    lines: list[str] = []

    # ── Pin definitions ──────────────────────────────────────────────
    io_nodes = list(dag.inputs) + list(dag.outputs)
    pin_defs = []
    for node in io_nodes:
        if node.alias:
            pin = dag.pin_map.get(node.alias, 0)
            pin_defs.append(f"const int PIN_{node.alias.upper()} = {pin};")
    if pin_defs:
        lines.append("// Pin definitions")
        lines.extend(pin_defs)
        lines.append("")

    # ── setup() ──────────────────────────────────────────────────────
    lines.append("void setup() {")
    for node in dag.inputs:
        if node.alias:
            lines.append(f"    pinMode(PIN_{node.alias.upper()}, INPUT);")
    for node in dag.outputs:
        if node.alias:
            lines.append(f"    pinMode(PIN_{node.alias.upper()}, OUTPUT);")
    lines.append("}")
    lines.append("")

    # ── Build variable name map ──────────────────────────────────────
    var_map: Dict[str, str] = {}

    # INPUT nodes: use alias if available, else input_{id}
    for node in dag.inputs:
        if node.alias:
            var_map[node.id] = _safe_name(node.alias)
        else:
            var_map[node.id] = f"input_{node.id}"

    # Gates (already topologically sorted): t1, t2, t3, ...
    for idx, gate in enumerate(dag.gates, start=1):
        var_map[gate.id] = f"t{idx}"

    # ── loop() ───────────────────────────────────────────────────────
    lines.append("void loop() {")

    # Emit input reads
    for node in dag.inputs:
        var_name = var_map[node.id]
        if node.alias:
            lines.append(
                f"    bool {var_name} = digitalRead(PIN_{node.alias.upper()});"
            )
        else:
            lines.append(
                f"    bool {var_name} = digitalRead("
                f"/* PIN for {node.id} */ 0);"
            )

    # Emit gate evaluations in topological order
    for idx, gate in enumerate(dag.gates, start=1):
        t_name = f"t{idx}"
        if gate.type == "NOT":
            if gate.inputs:
                src = _resolve_var(gate.inputs[0], var_map)
                lines.append(f"    bool {t_name} = !{src};")
            else:
                lines.append(
                    f"    bool {t_name} = false;  "
                    f"/* NOT gate {gate.id} has no inputs */"
                )
        elif gate.type == "AND":
            if len(gate.inputs) >= 2:
                a = _resolve_var(gate.inputs[0], var_map)
                b = _resolve_var(gate.inputs[1], var_map)
                lines.append(f"    bool {t_name} = {a} && {b};")
            else:
                lines.append(
                    f"    bool {t_name} = false;  "
                    f"/* AND gate {gate.id} needs 2 inputs */"
                )
        elif gate.type == "OR":
            if len(gate.inputs) >= 2:
                a = _resolve_var(gate.inputs[0], var_map)
                b = _resolve_var(gate.inputs[1], var_map)
                lines.append(f"    bool {t_name} = {a} || {b};")
            else:
                lines.append(
                    f"    bool {t_name} = false;  "
                    f"/* OR gate {gate.id} needs 2 inputs */"
                )
        elif gate.type == "XOR":
            if len(gate.inputs) >= 2:
                a = _resolve_var(gate.inputs[0], var_map)
                b = _resolve_var(gate.inputs[1], var_map)
                lines.append(f"    bool {t_name} = {a} ^ {b};")
            else:
                lines.append(
                    f"    bool {t_name} = false;  "
                    f"/* XOR gate {gate.id} needs 2 inputs */"
                )
        elif gate.type == "FUNCTION":
            if len(gate.inputs) >= 2:
                a = _resolve_var(gate.inputs[0], var_map)
                b = _resolve_var(gate.inputs[1], var_map)
                lines.append(
                    f"    bool {t_name} = {a} && {b};  "
                    f"/* FUNCTION treated as AND */"
                )
            else:
                lines.append(
                    f"    bool {t_name} = false;  "
                    f"/* FUNCTION gate {gate.id} */"
                )
        else:
            lines.append(
                f"    bool {t_name} = false;  "
                f"/* unknown gate type: {gate.type} */"
            )

    # Emit output writes
    for node in dag.outputs:
        if node.inputs:
            src = _resolve_var(node.inputs[0], var_map)
        else:
            src = "false"
        if node.alias:
            lines.append(f"    digitalWrite(PIN_{node.alias.upper()}, {src});")
        else:
            lines.append(
                f"    digitalWrite(/* PIN for {node.id} */ 0, {src});"
            )

    lines.append("    delay(10);")
    lines.append("}")

    return "\n".join(lines) + "\n"


__all__ = ["generate_arduino_sketch"]
