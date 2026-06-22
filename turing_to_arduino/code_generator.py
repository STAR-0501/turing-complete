from typing import Dict
from .circuit_parser import CircuitDAG, CircuitNode


def _safe_name(alias: str) -> str:
    """将别名转换为有效的 Arduino C 变量名。

    将非字母数字、非下划线字符替换为 '_'。
    如果名称以数字开头，则在前面加上 '_'。
    根据 Arduino C++ 约定将结果转换为小写。
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
    """查找给定节点 ID 的变量名。

    参数:
        node_id: 要解析的 CircuitNode.id。
        var_map: node_id 到 Arduino 变量名的映射。

    返回:
        变量名，如果未知则返回 C 注释占位符。
    """
    if node_id in var_map:
        return var_map[node_id]
    return f"/* unknown: {node_id} */"


def generate_arduino_sketch(dag: CircuitDAG) -> str:
    """将 CircuitDAG 转换为 Arduino .ino 草图字符串。

    生成的草图使用信号流变量方法：
    - INPUT 节点通过 digitalRead 读入 bool 变量。
    - 门电路（AND/OR/NOT/FUNCTION）按拓扑顺序求值，
      每个门输出到顺序编号的 bool 变量（t1, t2, ...）。
    - OUTPUT 节点通过 digitalWrite 写入源变量。

    参数:
        dag: 来自 circuit_parser 的拓扑排序 CircuitDAG。

    返回:
        一个完整的 Arduino .ino 文件字符串。
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

    # INPUT 节点：使用别名（如果可用），否则使用 input_{id}
    for node in dag.inputs:
        if node.alias:
            var_map[node.id] = _safe_name(node.alias)
        else:
            var_map[node.id] = f"input_{node.id}"

    # 门（已拓扑排序）: t1, t2, t3, ...
    for idx, gate in enumerate(dag.gates, start=1):
        var_map[gate.id] = f"t{idx}"

    # ── loop() ───────────────────────────────────────────────────────
    lines.append("void loop() {")

    # 生成输入读取代码
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

    # 按拓扑顺序生成门求值代码
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

    # 生成输出写入代码
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
