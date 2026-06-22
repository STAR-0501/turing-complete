"""将 Turing Complete 的 circuit_data.json 解析为带拓扑排序的 CircuitDAG。

处理 FUNCTION 模块展开、自动引脚映射和反馈回路检测。
仅使用 Python 标准库。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CircuitNode:
    """电路 DAG 中的单个节点。

    属性:
        id: 电路文件中的唯一元件标识符。
        type: 元件类型（AND, OR, NOT, INPUT, OUTPUT, FUNCTION）。
        alias: 人类可读的名称（例如 "A0", "SUM", "and_00"）。
        inputs: 连接到本节点输入端口的源节点 ID。
        output_to: 本节点输出所馈入的节点 ID。
    """

    id: str
    type: str
    alias: str
    inputs: list[str] = field(default_factory=list)
    output_to: list[str] = field(default_factory=list)


@dataclass
class CircuitDAG:
    """电路的拓扑排序有向无环图。

    属性:
        inputs: INPUT 节点，按别名排序。
        outputs: OUTPUT 节点，按别名排序。
        gates: AND/OR/NOT/FUNCTION 节点，拓扑排序。
        pin_map: 节点别名到 Arduino 数字引脚号的映射。
    """

    inputs: list[CircuitNode] = field(default_factory=list)
    outputs: list[CircuitNode] = field(default_factory=list)
    gates: list[CircuitNode] = field(default_factory=list)
    pin_map: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _generate_alias(element: dict[str, Any]) -> str:
    """当未给出别名时，从类型和 id 片段生成别名。"""
    alias: str | None = element.get("alias")
    if alias and alias.strip():
        return alias.strip()
    etype = element.get("type", "UNKNOWN")
    eid = element.get("id", "?")[:6]
    return f"{etype}_{eid}"


def _parse_wire_endpoint(
    wire: dict[str, Any], side: str
) -> tuple[str, str]:
    """从导线端点提取 (elementId, portId)。

    支持两种格式：
      1. 对象：``{"elementId": "...", "portId": "..."}``
      2. 字符串：``"elementId.portId"``
    """
    raw = wire.get(side)
    if raw is None:
        return ("", "")
    if isinstance(raw, str):
        parts = raw.split(".", 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")
    if isinstance(raw, dict):
        return (raw.get("elementId", ""), raw.get("portId", ""))
    return ("", "")


def _normalise_modules(
    modules_data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """将 modules_data 转换为以模块名称为键的字典。

    处理：
      - ``{"modules": [{"name": "X", "elements": [...], ...}, ...]}``
      - ``{"HalfAdder": {"elements": [...], ...}, ...}``
      - ``{"module_id": {"elements": [...], "name": "HalfAdder", ...}, ...}``
    """
    result: dict[str, dict[str, Any]] = {}
    if not modules_data:
        return result

    modules_list = modules_data.get("modules")
    if isinstance(modules_list, list):
        for mod in modules_list:
            name: str = mod.get("name") or mod.get("id") or ""
            if name:
                result[name] = mod
        return result

    for key, value in modules_data.items():
        if isinstance(value, dict) and "elements" in value:
            name: str = value.get("name", key)
            result[name] = value
    return result


def _resolve_signal_sources(
    elements: dict[str, dict[str, Any]],
    wires: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """将 element_id 映射到源元件 ID 列表（每个输入端口一个）。

    端口顺序遵循每个元件的 ``inputs`` 列表顺序。
    """
    # 将每个输入端口 id 映射到其输出连接到该端口的元件
    port_to_source: dict[str, str] = {}
    for w in wires:
        start_eid, _ = _parse_wire_endpoint(w, "start")
        _, end_pid = _parse_wire_endpoint(w, "end")
        if end_pid:
            port_to_source[end_pid] = start_eid

    result: dict[str, list[str]] = {}
    for eid, el in elements.items():
        sources: list[str] = []
        for port in el.get("inputs", []):
            src = port_to_source.get(port["id"])
            if src:
                sources.append(src)
        result[eid] = sources
    return result


def _resolve_output_targets(
    elements: dict[str, dict[str, Any]],
    wires: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """将 element_id 映射到消费元件 ID 列表。"""
    port_to_consumers: dict[str, list[str]] = {}
    for w in wires:
        start_eid, start_pid = _parse_wire_endpoint(w, "start")
        end_eid, _ = _parse_wire_endpoint(w, "end")
        if start_pid:
            port_to_consumers.setdefault(start_pid, []).append(end_eid)

    result: dict[str, list[str]] = {}
    for eid, el in elements.items():
        targets: list[str] = []
        for port in el.get("outputs", []):
            targets.extend(port_to_consumers.get(port["id"], []))
        # 去重同时保留插入顺序
        seen: set[str] = set()
        deduped = [t for t in targets if not (t in seen or seen.add(t))]
        result[eid] = deduped
    return result


# ---------------------------------------------------------------------------
# FUNCTION 展开
# ---------------------------------------------------------------------------


def _copy_wire_with_mapped_ids(
    wire: dict[str, Any],
    id_map: dict[str, str],
) -> dict[str, Any]:
    """深拷贝导线，通过 *id_map* 转换 elementId。"""
    new_wire = dict(wire)
    for side in ("start", "end"):
        ep = wire.get(side)
        if isinstance(ep, dict):
            new_ep = dict(ep)
            old_eid = ep.get("elementId", "")
            new_ep["elementId"] = id_map.get(old_eid, old_eid)
            new_wire[side] = new_ep
        elif isinstance(ep, str):
            parts = ep.split(".", 1)
            if len(parts) == 2:
                old_eid = parts[0]
                new_wire[side] = f"{id_map.get(old_eid, old_eid)}.{parts[1]}"
    return new_wire


def _get_module_definition(
    fn_el: dict[str, Any],
    modules_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """获取 FUNCTION 元件的模块定义。

    源优先级：
      1. 元件本身的 ``moduleData``（Turing Complete
         将模块数据内联保存在 circuit_data.json 中）。
      2. 通过别名在 *modules_lookup* 中查找（外部 modules_data.json）。
    """
    module_data: dict[str, Any] | None = fn_el.get("moduleData")
    if module_data is not None:
        return module_data

    fn_alias = _generate_alias(fn_el)
    mod_def = modules_lookup.get(fn_alias)
    if mod_def is None:
        raise ValueError(
            f"Unknown module '{fn_alias}' referenced by "
            f"element '{fn_el['id']}'"
        )
    return mod_def


def _expand_function_elements(
    elements: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    modules_lookup: dict[str, dict[str, Any]],
) -> None:
    """通过内联子电路**就地**展开 FUNCTION 元件。

    策略：
      1. 预先计算每个 FUNCTION 节点的外部源/目标。
      2. 获取模块定义（内联 ``moduleData`` 或通过别名外部查找）。
         使用模块定义中的 ``inputElementIds`` / ``outputElementIds``
         识别边界元件。
      3. 创建所有子元件的带前缀副本——包括边界元件
         （它们在重布线期间用作导线连接点）。
      4. 创建所有子导线的带前缀副本。
      5. For each boundary INPUT: rewire all sub-circuit wires that
         *start* at its output port — change their start to the external
         source's output port.  Then drop the boundary element.
      6. For each boundary OUTPUT: rewire all sub-circuit wires that
         *end* at its input port — change their end to the external
         target's input port.  Then drop the boundary element.
      7. Remove the original FUNCTION element.

    This avoids phantom bridge wires and keeps the wire graph consistent.
    """
    fn_indices = [
        i for i, el in enumerate(elements) if el.get("type") == "FUNCTION"
    ]
    if not fn_indices:
        return

    # 构建元件 id -> 索引映射，用于快速查找
    parent_elements: dict[str, dict[str, Any]] = {
        el["id"]: el for el in elements
    }
    parent_sources = _resolve_signal_sources(parent_elements, wires)
    parent_targets = _resolve_output_targets(parent_elements, wires)

    new_elements: list[dict[str, Any]] = []
    remove_ids: set[str] = set()

    for fn_idx in fn_indices:
        fn_el = elements[fn_idx]
        fn_id = fn_el["id"]
        remove_ids.add(fn_id)

        # 获取模块定义
        mod_def = _get_module_definition(fn_el, modules_lookup)

        sub_els: list[dict[str, Any]] = mod_def.get("elements", [])
        sub_wires: list[dict[str, Any]] = mod_def.get("wires", [])
        sub_input_ids: list[str] = mod_def.get("inputElementIds", [])
        sub_output_ids: list[str] = mod_def.get("outputElementIds", [])

        # 构建子电路的元件查找
        sub_elements_map: dict[str, dict[str, Any]] = {
            el["id"]: el for el in sub_els
        }

        # 解析边界元件
        sub_inputs: list[dict[str, Any]] = []
        for eid in sub_input_ids:
            el = sub_elements_map.get(eid)
            if el is not None:
                sub_inputs.append(el)

        sub_outputs: list[dict[str, Any]] = []
        for eid in sub_output_ids:
            el = sub_elements_map.get(eid)
            if el is not None:
                sub_outputs.append(el)

        prefix = f"_fn_{fn_id}"

        # 将旧的子元件 id 映射到带前缀的 id
        id_map: dict[str, str] = {
            el["id"]: f"{prefix}_{el['id']}" for el in sub_els
        }

        # 到此 FUNCTION 的外部连接
        ext_sources = parent_sources.get(fn_id, [])
        ext_targets = parent_targets.get(fn_id, [])

        # ----------------------------------------------------------------
        # 创建所有子元件的带前缀副本（包括边界元件）
        # ----------------------------------------------------------------
        for el in sub_els:
            new_el = dict(el)
            new_el["id"] = id_map[el["id"]]
            new_el["inputs"] = [dict(p) for p in el.get("inputs", [])]
            new_el["outputs"] = [dict(p) for p in el.get("outputs", [])]
            new_elements.append(new_el)

        # ----------------------------------------------------------------
        # 创建所有子导线的带前缀副本
        # ----------------------------------------------------------------
        mapped_sub_wires: list[dict[str, Any]] = []
        for w in sub_wires:
            mapped_sub_wires.append(_copy_wire_with_mapped_ids(w, id_map))

        # ----------------------------------------------------------------
        # 重布线：边界 INPUT -> 外部源
        # 查找从每个边界 INPUT 输出端口开始的子电路导线
        # 并将它们重定向到外部源。
        # ----------------------------------------------------------------
        for i, s_inp in enumerate(sub_inputs):
            if i >= len(ext_sources):
                break
            ext_src = ext_sources[i]
            s_inp_new_id = id_map[s_inp["id"]]
            s_inp_out_ports = s_inp.get("outputs", [])
            if not s_inp_out_ports:
                continue
            s_inp_out_port_id = s_inp_out_ports[0]["id"]

            # 查找外部源元件的输出端口
            ext_src_el = parent_elements.get(ext_src)
            ext_out_port_id: str = ""
            if ext_src_el:
                ext_ports = ext_src_el.get("outputs", [])
                if ext_ports:
                    ext_out_port_id = ext_ports[0]["id"]

            if not ext_out_port_id:
                continue

            # 重布线：将导线起点从子 INPUT 输出改为外部源
            for mw in mapped_sub_wires:
                start = mw.get("start", {})
                if isinstance(start, dict):
                    if (
                        start.get("elementId") == s_inp_new_id
                        and start.get("portId") == s_inp_out_port_id
                    ):
                        start["elementId"] = ext_src
                        start["portId"] = ext_out_port_id
                        start["isInput"] = False

        # ----------------------------------------------------------------
        # 重布线：边界 OUTPUT -> 外部目标
        # 查找结束于每个边界 OUTPUT 输入端口的子电路导线
        # 并将它们重定向到外部目标。
        # ----------------------------------------------------------------
        for i, s_out in enumerate(sub_outputs):
            if i >= len(ext_targets):
                break
            ext_tgt = ext_targets[i]
            s_out_new_id = id_map[s_out["id"]]
            s_out_in_ports = s_out.get("inputs", [])
            if not s_out_in_ports:
                continue
            s_out_in_port_id = s_out_in_ports[0]["id"]

            # 查找外部目标的输入端口
            ext_tgt_el = parent_elements.get(ext_tgt)
            ext_in_port_id: str = ""
            if ext_tgt_el:
                tgt_ports = ext_tgt_el.get("inputs", [])
                if tgt_ports:
                    ext_in_port_id = tgt_ports[0]["id"]

            if not ext_in_port_id:
                continue

            # 重布线：将导线终点从子 OUTPUT 输入改为外部目标
            for mw in mapped_sub_wires:
                end = mw.get("end", {})
                if isinstance(end, dict):
                    if (
                        end.get("elementId") == s_out_new_id
                        and end.get("portId") == s_out_in_port_id
                    ):
                        end["elementId"] = ext_tgt
                        end["portId"] = ext_in_port_id
                        end["isInput"] = True

        # ----------------------------------------------------------------
        # 移除边界元件（它们已被重布线替换）
        # ----------------------------------------------------------------
        boundary_ids: set[str] = {
            id_map[el["id"]]
            for el in (*sub_inputs, *sub_outputs)
        }
        new_elements = [
            el for el in new_elements if el["id"] not in boundary_ids
        ]

        # 将重布线后的子电路导线添加到主导线列表
        wires.extend(mapped_sub_wires)

    # 移除原始 FUNCTION 元件
    elements[:] = [el for el in elements if el["id"] not in remove_ids]
    # 添加非边界子元件
    elements.extend(new_elements)


# ---------------------------------------------------------------------------
# Topological sort (Kahn)
# ---------------------------------------------------------------------------


def _kahn_sort(gates: list[CircuitNode]) -> list[CircuitNode]:
    """使用 Kahn 算法对门节点进行拓扑排序。

    如果检测到循环（反馈回路）则引发 ValueError。
    """
    gate_by_id: dict[str, CircuitNode] = {n.id: n for n in gates}
    gate_ids: set[str] = set(gate_by_id)

    # 入度：每个门依赖于多少其他门输入
    in_degree: dict[str, int] = {}
    for gn in gates:
        deg = sum(1 for src in gn.inputs if src in gate_ids)
        in_degree[gn.id] = deg

    queue: deque[str] = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )

    sorted_nodes: list[CircuitNode] = []
    while queue:
        cid = queue.popleft()
        cn = gate_by_id.get(cid)
        if cn is None:
            continue
        sorted_nodes.append(cn)

        for tgt_id in cn.output_to:
            if tgt_id in gate_ids:
                in_degree[tgt_id] -= 1
                if in_degree[tgt_id] == 0:
                    queue.append(tgt_id)

    if len(sorted_nodes) != len(gates):
        remaining = len(gates) - len(sorted_nodes)
        raise ValueError(
            f"Circuit contains feedback loop (unsupported); "
            f"{remaining} gate(s) could not be topologically sorted"
        )
    return sorted_nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_circuit(
    data: dict[str, Any],
    modules_data: dict[str, Any] | None = None,
) -> CircuitDAG:
    """将 Turing Complete 电路解析为拓扑排序的 CircuitDAG。

    参数：
        data: 解析后的 ``circuit_data.json`` 内容。
        modules_data: 解析后的 ``modules_data.json`` 内容（可选）。
            用于将 FUNCTION 元件展开为其子电路。

    返回：
        一个包含 inputs、outputs、gates（拓扑排序）和自动分配的 pin_map 的 CircuitDAG。

    抛出：
        ValueError: 如果电路包含反馈回路或超过最大 I/O 引脚数（12）。
    """
    raw_elements: list[dict[str, Any]] = data.get("elements", [])
    raw_wires: list[dict[str, Any]] = data.get("wires", [])

    # 如果有模块数据，展开 FUNCTION 模块
    modules_lookup = _normalise_modules(modules_data)
    if modules_lookup and any(
        el.get("type") == "FUNCTION" for el in raw_elements
    ):
        _expand_function_elements(raw_elements, raw_wires, modules_lookup)

    # 构建元件 id 到元件的查找表
    all_elements: dict[str, dict[str, Any]] = {
        el["id"]: el for el in raw_elements
    }

    signal_sources = _resolve_signal_sources(all_elements, raw_wires)
    output_targets = _resolve_output_targets(all_elements, raw_wires)

    # 对元件分类并构建 CircuitNode
    nodes: dict[str, CircuitNode] = {}
    input_nodes: list[CircuitNode] = []
    output_nodes: list[CircuitNode] = []
    gate_nodes: list[CircuitNode] = []

    for el in raw_elements:
        eid = el["id"]
        etype = el.get("type", "")
        alias = _generate_alias(el)
        sources = signal_sources.get(eid, [])
        targets = output_targets.get(eid, [])

        node = CircuitNode(
            id=eid,
            type=etype,
            alias=alias,
            inputs=list(sources),
            output_to=list(targets),
        )
        nodes[eid] = node

        if etype == "INPUT":
            input_nodes.append(node)
        elif etype == "OUTPUT":
            output_nodes.append(node)
        else:
            gate_nodes.append(node)

    # 对门进行拓扑排序
    sorted_gates = _kahn_sort(gate_nodes)

    # 按别名排序 I/O 并分配引脚映射
    input_nodes.sort(key=lambda n: n.alias)
    output_nodes.sort(key=lambda n: n.alias)

    total_io = len(input_nodes) + len(output_nodes)
    if total_io > 12:
        raise ValueError(
            f"Too many I/O pins (max 12), got {total_io}"
        )

    pin_map: dict[str, int] = {}
    for i, inp in enumerate(input_nodes):
        pin_map[inp.alias] = 2 + i  # D2, D3, ...
    for i, out in enumerate(output_nodes):
        pin_map[out.alias] = 8 + i  # D8, D9, ...

    return CircuitDAG(
        inputs=input_nodes,
        outputs=output_nodes,
        gates=sorted_gates,
        pin_map=pin_map,
    )
