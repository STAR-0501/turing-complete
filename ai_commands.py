import json
import os
import random
import string

def generate_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))

class CircuitManager:
    def __init__(self, data_file):
        self.data_file = data_file

    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"elements": [], "wires": []}

    def _save_data(self, data):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_state(self):
        return self._load_data()

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
                "inputs": [{"id": generate_id(), "x": -5, "y": 15}, {"id": generate_id(), "x": -5, "y": 45}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30}]
            })
        elif element_type == 'OR':
            element.update({
                "width": 80, "height": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 15}, {"id": generate_id(), "x": -5, "y": 45}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30}]
            })
        elif element_type == 'NOT':
            element.update({
                "width": 80, "height": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 30}],
                "outputs": [{"id": generate_id(), "x": 85, "y": 30}]
            })
        elif element_type == 'INPUT':
            element.update({
                "width": 60, "height": 60,
                "inputs": [],
                "outputs": [{"id": generate_id(), "x": 65, "y": 30}]
            })
        elif element_type == 'OUTPUT':
            element.update({
                "width": 60, "height": 60,
                "inputs": [{"id": generate_id(), "x": -5, "y": 30}],
                "outputs": []
            })
        else:
            raise ValueError(f"Unknown element type: {element_type}")

        data["elements"].append(element)
        self._save_data(data)
        return element

    def remove_element(self, element_id):
        data = self._load_data()
        # Remove the element
        data["elements"] = [e for e in data["elements"] if e["id"] != element_id]
        # Remove associated wires
        data["wires"] = [w for w in data["wires"] if w["from"]["elementId"] != element_id and w["to"]["elementId"] != element_id]
        self._save_data(data)
        return True

    def add_wire(self, from_id, from_port_idx, to_id, to_port_idx):
        data = self._load_data()
        
        from_el = next((e for e in data["elements"] if e["id"] == from_id), None)
        to_el = next((e for e in data["elements"] if e["id"] == to_id), None)
        
        if not from_el or not to_el:
            raise ValueError("Invalid element IDs")
            
        wire = {
            "id": generate_id(),
            "from": {
                "elementId": from_id,
                "portId": from_el["outputs"][from_port_idx]["id"]
            },
            "to": {
                "elementId": to_id,
                "portId": to_el["inputs"][to_port_idx]["id"]
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

    def toggle_input(self, element_id):
        data = self._load_data()
        for e in data["elements"]:
            if e["id"] == element_id and e["type"] == 'INPUT':
                e["state"] = not e.get("state", False)
                break
        self._save_data(data)
        return True
