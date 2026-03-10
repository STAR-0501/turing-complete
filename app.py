from flask import Flask, request, jsonify, render_template
import json
import os

app = Flask(__name__)

# 存储电路数据的文件
CIRCUIT_DATA_FILE = 'circuit_data.json'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/save-circuit', methods=['POST'])
def save_circuit():
    try:
        data = request.json
        with open(CIRCUIT_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({'status': 'success', 'message': 'Circuit saved successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/load-circuit', methods=['GET'])
def load_circuit():
    try:
        if os.path.exists(CIRCUIT_DATA_FILE):
            with open(CIRCUIT_DATA_FILE, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({'elements': [], 'wires': []})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)