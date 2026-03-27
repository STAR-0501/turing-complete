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

    def add_element(self, element_type, x, y):
        data = self._load_data()
        
        # Define element structures (matching elements.js)
        element = {
            "id": generate_id(),
            "type": element_type,
            "x": x,
            "y": y,
            "state": False
        }

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

    def toggle_input(self, element_id):
        data = self._load_data()
        for e in data["elements"]:
            if e["id"] == element_id and e["type"] == 'INPUT':
                e["state"] = not e.get("state", False)
                break
        self._save_data(data)
        return True
