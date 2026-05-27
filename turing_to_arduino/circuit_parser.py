"""Parse Turing Complete circuit_data.json into CircuitDAG with topological sort.

Handles FUNCTION module expansion, auto pin mapping, and feedback loop detection.
Python standard library only.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CircuitNode:
    """A single node in the circuit DAG.

    Attributes:
        id: Unique element identifier from the circuit file.
        type: Element type (AND, OR, NOT, INPUT, OUTPUT, FUNCTION).
        alias: Human-readable name (e.g. "A0", "SUM", "and_00").
        inputs: Source node IDs connected to this node's input ports.
        output_to: Node IDs that this node's output feeds into.
    """

    id: str
    type: str
    alias: str
    inputs: list[str] = field(default_factory=list)
    output_to: list[str] = field(default_factory=list)


@dataclass
class CircuitDAG:
    """A topologically-sorted directed acyclic graph of the circuit.

    Attributes:
        inputs: INPUT nodes, sorted by alias.
        outputs: OUTPUT nodes, sorted by alias.
        gates: AND/OR/NOT/FUNCTION nodes, topologically sorted.
        pin_map: Mapping from node alias to Arduino digital pin number.
    """

    inputs: list[CircuitNode] = field(default_factory=list)
    outputs: list[CircuitNode] = field(default_factory=list)
    gates: list[CircuitNode] = field(default_factory=list)
    pin_map: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_alias(element: dict[str, Any]) -> str:
    """Generate an alias from type and id fragment when none is given."""
    alias: str | None = element.get("alias")
    if alias and alias.strip():
        return alias.strip()
    etype = element.get("type", "UNKNOWN")
    eid = element.get("id", "?")[:6]
    return f"{etype}_{eid}"


def _parse_wire_endpoint(
    wire: dict[str, Any], side: str
) -> tuple[str, str]:
    """Extract (elementId, portId) from a wire endpoint.

    Supports two formats:
      1. Object: ``{"elementId": "...", "portId": "..."}``
      2. String: ``"elementId.portId"``
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
    """Convert modules_data into a dict keyed by module name.

    Handles:
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
    """Map element_id -> list of source element IDs (one per input port).

    Port ordering follows each element's ``inputs`` list order.
    """
    # Map each input-port id to the element whose output connects there
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
    """Map element_id -> list of consumer element IDs."""
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
        # Deduplicate while preserving insertion order
        seen: set[str] = set()
        deduped = [t for t in targets if not (t in seen or seen.add(t))]
        result[eid] = deduped
    return result


# ---------------------------------------------------------------------------
# FUNCTION expansion
# ---------------------------------------------------------------------------


def _copy_wire_with_mapped_ids(
    wire: dict[str, Any],
    id_map: dict[str, str],
) -> dict[str, Any]:
    """Deep-copy a wire, translating elementIds through *id_map*."""
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
    """Get the module definition for a FUNCTION element.

    Source priority:
      1. Inline ``moduleData`` on the element itself (Turing Complete
         saves module data inline in circuit_data.json).
      2. Lookup by alias in *modules_lookup* (external modules_data.json).
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
    """Expand FUNCTION elements **in-place** by inlining sub-circuits.

    Strategy:
      1. Pre-compute external sources/targets for each FUNCTION node.
      2. Get the module definition (inline ``moduleData`` or external
         lookup by alias).  Use ``inputElementIds`` / ``outputElementIds``
         from the module definition to identify boundary elements.
      3. Create prefixed copies of all sub-elements — boundary included
         (they serve as wire connection points during rewiring).
      4. Create prefixed copies of all sub-wires.
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

    # Build element-id -> index map for fast lookup
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

        # Get module definition
        mod_def = _get_module_definition(fn_el, modules_lookup)

        sub_els: list[dict[str, Any]] = mod_def.get("elements", [])
        sub_wires: list[dict[str, Any]] = mod_def.get("wires", [])
        sub_input_ids: list[str] = mod_def.get("inputElementIds", [])
        sub_output_ids: list[str] = mod_def.get("outputElementIds", [])

        # Build element lookup for sub-circuit
        sub_elements_map: dict[str, dict[str, Any]] = {
            el["id"]: el for el in sub_els
        }

        # Resolve boundary elements
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

        # Map old sub-element ids -> prefixed ids
        id_map: dict[str, str] = {
            el["id"]: f"{prefix}_{el['id']}" for el in sub_els
        }

        # External connections to this FUNCTION
        ext_sources = parent_sources.get(fn_id, [])
        ext_targets = parent_targets.get(fn_id, [])

        # ----------------------------------------------------------------
        # Create prefixed copies of ALL sub-elements (boundary included)
        # ----------------------------------------------------------------
        for el in sub_els:
            new_el = dict(el)
            new_el["id"] = id_map[el["id"]]
            new_el["inputs"] = [dict(p) for p in el.get("inputs", [])]
            new_el["outputs"] = [dict(p) for p in el.get("outputs", [])]
            new_elements.append(new_el)

        # ----------------------------------------------------------------
        # Create prefixed copies of all sub-wires
        # ----------------------------------------------------------------
        mapped_sub_wires: list[dict[str, Any]] = []
        for w in sub_wires:
            mapped_sub_wires.append(_copy_wire_with_mapped_ids(w, id_map))

        # ----------------------------------------------------------------
        # Rewire: boundary INPUT -> external source
        # Find all sub-circuit wires starting at each boundary INPUT's
        # output port and redirect them to the external source.
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

            # Find the external source element's output port
            ext_src_el = parent_elements.get(ext_src)
            ext_out_port_id: str = ""
            if ext_src_el:
                ext_ports = ext_src_el.get("outputs", [])
                if ext_ports:
                    ext_out_port_id = ext_ports[0]["id"]

            if not ext_out_port_id:
                continue

            # Rewire: change wire start from sub-INPUT output to external source
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
        # Rewire: boundary OUTPUT -> external target
        # Find all sub-circuit wires ending at each boundary OUTPUT's
        # input port and redirect them to the external target.
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

            # Find the external target's input port
            ext_tgt_el = parent_elements.get(ext_tgt)
            ext_in_port_id: str = ""
            if ext_tgt_el:
                tgt_ports = ext_tgt_el.get("inputs", [])
                if tgt_ports:
                    ext_in_port_id = tgt_ports[0]["id"]

            if not ext_in_port_id:
                continue

            # Rewire: change wire end from sub-OUTPUT input to external target
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
        # Drop boundary elements (they've been replaced by rewiring)
        # ----------------------------------------------------------------
        boundary_ids: set[str] = {
            id_map[el["id"]]
            for el in (*sub_inputs, *sub_outputs)
        }
        new_elements = [
            el for el in new_elements if el["id"] not in boundary_ids
        ]

        # Add the rewired sub-circuit wires to the main wire list
        wires.extend(mapped_sub_wires)

    # Remove original FUNCTION elements
    elements[:] = [el for el in elements if el["id"] not in remove_ids]
    # Add non-boundary sub-elements
    elements.extend(new_elements)


# ---------------------------------------------------------------------------
# Topological sort (Kahn)
# ---------------------------------------------------------------------------


def _kahn_sort(gates: list[CircuitNode]) -> list[CircuitNode]:
    """Topologically sort gate nodes using Kahn's algorithm.

    Raises ValueError if a cycle (feedback loop) is detected.
    """
    gate_by_id: dict[str, CircuitNode] = {n.id: n for n in gates}
    gate_ids: set[str] = set(gate_by_id)

    # in-degree: how many *other gate* inputs each gate depends on
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
    """Parse a Turing Complete circuit into a topologically-sorted CircuitDAG.

    Args:
        data: Parsed ``circuit_data.json`` content.
        modules_data: Parsed ``modules_data.json`` content (optional).
            Used to expand FUNCTION elements into their sub-circuits.

    Returns:
        A CircuitDAG with inputs, outputs, gates (topologically sorted),
        and an auto-assigned ``pin_map``.

    Raises:
        ValueError: If the circuit contains feedback loops or exceeds
            the maximum I/O pin count (12).
    """
    raw_elements: list[dict[str, Any]] = data.get("elements", [])
    raw_wires: list[dict[str, Any]] = data.get("wires", [])

    # Expand FUNCTION modules if module data is available
    modules_lookup = _normalise_modules(modules_data)
    if modules_lookup and any(
        el.get("type") == "FUNCTION" for el in raw_elements
    ):
        _expand_function_elements(raw_elements, raw_wires, modules_lookup)

    # Build element-id -> element lookup
    all_elements: dict[str, dict[str, Any]] = {
        el["id"]: el for el in raw_elements
    }

    signal_sources = _resolve_signal_sources(all_elements, raw_wires)
    output_targets = _resolve_output_targets(all_elements, raw_wires)

    # Classify elements and build CircuitNodes
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

    # Topological sort for gates
    sorted_gates = _kahn_sort(gate_nodes)

    # Sort I/O by alias and assign pin map
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
