import json
import os
import random
import string

def generate_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))

class CircuitManager:
    def __init__(self, data_file, functions_file=None):
        self.data_file = data_file
        self.functions_file = functions_file

    def _load_functions(self):
        if self.functions_file and os.path.exists(self.functions_file):
            with open(self.functions_file, 'r', encoding='utf-8') as f:
                return json.load(f).get("functions", [])
        return []

    def _save_functions(self, functions):
        if self.functions_file:
            with open(self.functions_file, 'w', encoding='utf-8') as f:
                json.dump({"functions": functions}, f, indent=2, ensure_ascii=False)

    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"elements": [], "wires": []}

    def _save_data(self, data):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _build_endpoint(self, element, port_id, is_input):
        ports = element.get("inputs", []) if is_input else element.get("outputs", [])
        port = next((p for p in ports if p.get("id") == port_id), None)
        if not port:
            return None
        return {
            "elementId": element["id"],
            "portId": port_id,
            "x": element.get("x", 0) + port.get("x", 0),
            "y": element.get("y", 0) + port.get("y", 0),
            "isInput": is_input
        }

    def _normalize_wire(self, wire, elements):
        if "start" in wire and "end" in wire:
            start = wire.get("start", {})
            end = wire.get("end", {})
            start_el = next((e for e in elements if e.get("id") == start.get("elementId")), None)
            end_el = next((e for e in elements if e.get("id") == end.get("elementId")), None)
            if not start_el or not end_el:
                return None

            start_is_input = start.get("isInput")
            if start_is_input is None:
                start_is_input = any(p.get("id") == start.get("portId") for p in start_el.get("inputs", []))
            end_is_input = end.get("isInput")
            if end_is_input is None:
                end_is_input = any(p.get("id") == end.get("portId") for p in end_el.get("inputs", []))

            normalized_start = self._build_endpoint(start_el, start.get("portId"), start_is_input)
            normalized_end = self._build_endpoint(end_el, end.get("portId"), end_is_input)
            if not normalized_start or not normalized_end:
                return None

            normalized = {
                "id": wire.get("id", generate_id()),
                "start": normalized_start,
                "end": normalized_end
            }
            if "state" in wire:
                normalized["state"] = wire["state"]
            return normalized

        if "from" in wire and "to" in wire:
            from_data = wire.get("from", {})
            to_data = wire.get("to", {})
            from_el = next((e for e in elements if e.get("id") == from_data.get("elementId")), None)
            to_el = next((e for e in elements if e.get("id") == to_data.get("elementId")), None)
            if not from_el or not to_el:
                return None

            start = self._build_endpoint(from_el, from_data.get("portId"), False)
            end = self._build_endpoint(to_el, to_data.get("portId"), True)
            if not start or not end:
                return None

            normalized = {
                "id": wire.get("id", generate_id()),
                "start": start,
                "end": end
            }
            if "state" in wire:
                normalized["state"] = wire["state"]
            return normalized

        return None

    def _normalize_data(self, data):
        elements = data.get("elements", [])
        wires = data.get("wires", [])
        normalized_wires = []
        for wire in wires:
            normalized_wire = self._normalize_wire(wire, elements)
            if normalized_wire:
                normalized_wires.append(normalized_wire)
        data["wires"] = normalized_wires
        return data

    def get_state(self):
        data = self._load_data()
        normalized = self._normalize_data(data)
        return normalized

    def add_element(self, element_type, x, y, alias=None):
        data = self._load_data()
        
        # Define element structures (matching elements.js)
        element = {
            "id": generate_id(),
            "type": element_type,
            "x": x,
            "y": y,
            "state": False
        }
        if alias:
            element["alias"] = str(alias)

        if element_type == 'AND':
            element.update({
                "width": 80, "height": 60,
                "realWidth": 80, "realHeight": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 15, "realX": -5, "realY": 15}, {"id": generate_id(), "x": -5, "y": 45, "realX": -5, "realY": 45}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30, "realX": 85, "realY": 30}]
            })
        elif element_type == 'OR':
            element.update({
                "width": 80, "height": 60,
                "realWidth": 80, "realHeight": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 15, "realX": -5, "realY": 15}, {"id": generate_id(), "x": -5, "y": 45, "realX": -5, "realY": 45}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30, "realX": 85, "realY": 30}]
            })
        elif element_type == 'NOT':
            element.update({
                "width": 80, "height": 60,
                "realWidth": 80, "realHeight": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 30, "realX": -5, "realY": 30}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30, "realX": 85, "realY": 30}]
            })
        elif element_type == 'INPUT':
            element.update({
                "width": 60, "height": 60,
                "realWidth": 60, "realHeight": 60,
                "inputs": [],
                "outputs": [{"id": generate_id(), "x": 65, "y": 30, "realX": 65, "realY": 30}]
            })
        elif element_type == 'OUTPUT':
            element.update({
                "width": 60, "height": 60,
                "realWidth": 60, "realHeight": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 30, "realX": -5, "realY": 30}],
                "outputs": []
            })
        else:
            # Check if it's a function
            functions = self._load_functions()
            func = next((f for f in functions if f.get("name") == element_type), None)
            if func:
                input_count = len(func.get("inputElementIds", []))
                output_count = len(func.get("outputElementIds", []))
                height = max(60, max(input_count, output_count) * 25 + 20)
                
                inputs = []
                for i in range(input_count):
                    inputs.append({
                        "id": generate_id(),
                        "x": -5,
                        "y": 20 + i * 25,
                        "realX": -5,
                        "realY": 20 + i * 25
                    })
                
                outputs = []
                for i in range(output_count):
                    outputs.append({
                        "id": generate_id(),
                        "x": 105,
                        "y": 20 + i * 25,
                        "realX": 105,
                        "realY": 20 + i * 25
                    })
                
                element.update({
                    "type": "FUNCTION",
                    "name": element_type,
                    "width": 100,
                    "height": height,
                    "realWidth": 100,
                    "realHeight": height,
                    "inputs": inputs,
                    "outputs": outputs,
                    "functionData": {
                        "elements": func.get("elements", []),
                        "wires": func.get("wires", []),
                        "inputElementIds": func.get("inputElementIds", []),
                        "outputElementIds": func.get("outputElementIds", [])
                    }
                })
            else:
                raise ValueError(f"Unknown element type: {element_type}")

        data["elements"].append(element)
        self._save_data(data)
        return element

    def remove_element(self, element_id):
        data = self._normalize_data(self._load_data())
        data["elements"] = [e for e in data["elements"] if e["id"] != element_id]
        data["wires"] = [
            w for w in data["wires"]
            if w["start"]["elementId"] != element_id and w["end"]["elementId"] != element_id
        ]
        self._save_data(data)
        return True

    def add_wire(self, from_id, from_port_idx, to_id, to_port_idx):
        data = self._normalize_data(self._load_data())
        
        from_el = next((e for e in data["elements"] if e["id"] == from_id), None)
        to_el = next((e for e in data["elements"] if e["id"] == to_id), None)
        
        if not from_el or not to_el:
            raise ValueError("Invalid element IDs")

        from_outputs = from_el.get("outputs", [])
        to_inputs = to_el.get("inputs", [])
        if from_port_idx < 0 or from_port_idx >= len(from_outputs):
            raise ValueError("Invalid source output port index")
        if to_port_idx < 0 or to_port_idx >= len(to_inputs):
            raise ValueError("Invalid target input port index")
            
        from_port = from_outputs[from_port_idx]
        to_port = to_inputs[to_port_idx]
        wire = {
            "id": generate_id(),
            "start": {
                "elementId": from_id,
                "portId": from_port["id"],
                "x": from_el.get("x", 0) + from_port.get("x", 0),
                "y": from_el.get("y", 0) + from_port.get("y", 0),
                "isInput": False
            },
            "end": {
                "elementId": to_id,
                "portId": to_port["id"],
                "x": to_el.get("x", 0) + to_port.get("x", 0),
                "y": to_el.get("y", 0) + to_port.get("y", 0),
                "isInput": True
            }
        }
        
        data["wires"].append(wire)
        self._save_data(data)
        return wire

    def remove_wire(self, wire_id):
        data = self._load_data()
        data["wires"] = [w for w in data["wires"] if w["id"] != wire_id]
        self._save_data(data)
        return True

    def clear_circuit(self):
        self._save_data({"elements": [], "wires": []})
        return True

    def define_function(self, name):
        data = self._load_data()
        elements = data.get("elements", [])
        wires = data.get("wires", [])
        
        input_ids = [e["id"] for e in elements if e.get("type") == "INPUT"]
        output_ids = [e["id"] for e in elements if e.get("type") == "OUTPUT"]
        
        if not input_ids or not output_ids:
            raise ValueError("A function must have at least one INPUT and one OUTPUT.")
            
        functions = self._load_functions()
        functions = [f for f in functions if f.get("name") != name]
        
        func_data = {
            "id": generate_id(),
            "name": name,
            "elements": elements,
            "wires": wires,
            "inputElementIds": input_ids,
            "outputElementIds": output_ids
        }
        
        functions.append(func_data)
        self._save_functions(functions)
        return func_data

    def move_element(self, element_id, x, y):
        data = self._load_data()
        for e in data["elements"]:
            if e["id"] == element_id:
                dx = x - e.get("x", 0)
                dy = y - e.get("y", 0)
                e["x"] = x
                e["y"] = y
                for w in data.get("wires", []):
                    if w["start"]["elementId"] == element_id:
                        w["start"]["x"] += dx
                        w["start"]["y"] += dy
                    if w["end"]["elementId"] == element_id:
                        w["end"]["x"] += dx
                        w["end"]["y"] += dy
                break
        self._save_data(data)
        return True

    def toggle_input(self, element_id):
        data = self._load_data()
        for e in data["elements"]:
            if e["id"] == element_id and e["type"] == 'INPUT':
                e["state"] = not e.get("state", False)
                break
        self._save_data(data)
        self.simulate()
        return True

    def set_input(self, element_id, value):
        data = self._load_data()
        found = False
        for e in data.get("elements", []):
            if e.get("id") == element_id and e.get("type") == 'INPUT':
                e["state"] = bool(value)
                found = True
                break
        if not found:
            raise ValueError("INPUT element not found")
        self._save_data(data)
        self.simulate()
        return True

    def sample_outputs(self, output_ids=None):
        self.simulate()
        data = self._load_data()
        elements = data.get("elements", [])
        outputs = [e for e in elements if e.get("type") == "OUTPUT"]

        if output_ids:
            id_set = set(output_ids)
            missing = [oid for oid in output_ids if oid not in {o.get("id") for o in outputs}]
            if missing:
                raise ValueError(f"Unknown OUTPUT id(s): {', '.join(missing)}")
            outputs = [o for o in outputs if o.get("id") in id_set]

        return {
            "outputs": [
                {"id": o.get("id"), "alias": o.get("alias") or o.get("name"), "state": bool(o.get("state", False))}
                for o in outputs
            ]
        }

    def _get_input_source_state(self, elements, wires, target_element_id, target_port_id):
        def _get_output_value(src_el, src_port_id):
            if not src_el:
                return False
            if src_el.get("type") == "FUNCTION":
                outputs = src_el.get("outputs") or []
                out_idx = None
                for i, p in enumerate(outputs):
                    if p.get("id") == src_port_id:
                        out_idx = i
                        break
                if out_idx is not None:
                    output_states = src_el.get("outputStates") or []
                    if out_idx < len(output_states):
                        return bool(output_states[out_idx])
            return bool(src_el.get("state", False))

        for w in wires:
            start = w.get("start", {})
            end = w.get("end", {})
            if end.get("elementId") == target_element_id and end.get("portId") == target_port_id:
                src_id = start.get("elementId")
                src_el = next((e for e in elements if e.get("id") == src_id), None)
                if src_el:
                    return _get_output_value(src_el, start.get("portId"))
            if start.get("elementId") == target_element_id and start.get("portId") == target_port_id:
                src_id = end.get("elementId")
                src_el = next((e for e in elements if e.get("id") == src_id), None)
                if src_el:
                    return _get_output_value(src_el, end.get("portId"))
        return None

    def _has_input_connection(self, wires, target_element_id, target_port_id):
        for w in wires:
            start = w.get("start", {})
            end = w.get("end", {})
            if end.get("elementId") == target_element_id and end.get("portId") == target_port_id:
                return True
            if start.get("elementId") == target_element_id and start.get("portId") == target_port_id:
                return True
        return False

    def _simulate_elements_until_stable(self, elements, wires, function_cache, max_iters=50, depth=0):
        for _ in range(max_iters):
            changed = False
            for el in elements:
                el_type = el.get("type")
                if el_type == "INPUT":
                    continue

                old_state = bool(el.get("state", False))
                new_state = old_state

                if el_type == "AND":
                    all_connected = True
                    all_true = True
                    for p in el.get("inputs", []):
                        if not self._has_input_connection(wires, el.get("id"), p.get("id")):
                            all_connected = False
                            break
                        v = self._get_input_source_state(elements, wires, el.get("id"), p.get("id"))
                        if v is not True:
                            all_true = False
                            break
                    new_state = bool(all_connected and all_true)
                elif el_type == "OR":
                    has_input = False
                    any_true = False
                    for p in el.get("inputs", []):
                        if self._has_input_connection(wires, el.get("id"), p.get("id")):
                            has_input = True
                            v = self._get_input_source_state(elements, wires, el.get("id"), p.get("id"))
                            if v is True:
                                any_true = True
                                break
                    new_state = bool(has_input and any_true)
                elif el_type == "NOT":
                    has_input = False
                    input_true = False
                    for p in el.get("inputs", []):
                        if self._has_input_connection(wires, el.get("id"), p.get("id")):
                            has_input = True
                            v = self._get_input_source_state(elements, wires, el.get("id"), p.get("id"))
                            if v is True:
                                input_true = True
                                break
                    new_state = bool(has_input and (not input_true))
                elif el_type == "OUTPUT":
                    input_true = False
                    for p in el.get("inputs", []):
                        if self._has_input_connection(wires, el.get("id"), p.get("id")):
                            v = self._get_input_source_state(elements, wires, el.get("id"), p.get("id"))
                            if v is True:
                                input_true = True
                                break
                    new_state = bool(input_true)
                elif el_type == "FUNCTION":
                    old_output_states = list(el.get("outputStates") or [])
                    output_states = self._calculate_function_element(el, elements, wires, function_cache, depth=depth)
                    el["outputStates"] = output_states
                    new_state = bool(output_states[0]) if output_states else False
                    if output_states != old_output_states:
                        changed = True

                if new_state != old_state:
                    el["state"] = new_state
                    changed = True
                elif el_type == "FUNCTION":
                    el["state"] = new_state

            if not changed:
                break

    def _calculate_function_element(self, function_element, parent_elements, parent_wires, function_cache, depth=0):
        if depth >= 10:
            return []
        function_data = function_element.get("functionData") or {}
        func_elements = json.loads(json.dumps(function_data.get("elements") or []))
        func_wires = json.loads(json.dumps(function_data.get("wires") or []))
        input_element_ids = function_data.get("inputElementIds") or []
        output_element_ids = function_data.get("outputElementIds") or []

        for i, input_port in enumerate(function_element.get("inputs", []) or []):
            input_state = self._get_input_source_state(parent_elements, parent_wires, function_element.get("id"), input_port.get("id"))
            if i < len(input_element_ids):
                internal_input = next((e for e in func_elements if e.get("id") == input_element_ids[i]), None)
                if internal_input is not None:
                    internal_input["state"] = bool(input_state) if input_state is not None else False

        self._simulate_elements_until_stable(func_elements, func_wires, function_cache, depth=depth + 1)

        output_states = []
        for out_id in output_element_ids:
            out_el = next((e for e in func_elements if e.get("id") == out_id), None)
            output_states.append(bool(out_el.get("state", False)) if out_el else False)
        return output_states

    def simulate(self):
        data = self._load_data()
        elements = data.get("elements", [])
        wires = data.get("wires", [])
        function_cache = {}
        self._simulate_elements_until_stable(elements, wires, function_cache)
        self._save_data(data)
        return True
