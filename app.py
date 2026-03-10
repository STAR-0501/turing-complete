from flask import Flask, request, jsonify, render_template
import json
import os

app = Flask(__name__)

# 获取当前文件所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 存储电路数据的文件
CIRCUIT_DATA_FILE = os.path.join(BASE_DIR, 'circuit_data.json')

# 初始化：如果文件不存在，创建一个空的电路数据文件
def init_circuit_file():
    if not os.path.exists(CIRCUIT_DATA_FILE):
        try:
            with open(CIRCUIT_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'elements': [], 'wires': []}, f, indent=2, ensure_ascii=False)
            print(f"已创建空的电路数据文件: {CIRCUIT_DATA_FILE}")
        except Exception as e:
            print(f"创建电路数据文件失败: {e}")

# 启动时初始化
init_circuit_file()

@app.after_request
def after_request(response):
    # 添加CORS响应头
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/save-circuit', methods=['POST', 'OPTIONS'])
def save_circuit():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        # 写入文件
        with open(CIRCUIT_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"电路数据已保存到: {CIRCUIT_DATA_FILE}")
        return jsonify({'status': 'success', 'message': 'Circuit saved successfully'})
    except Exception as e:
        print(f"保存电路数据失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/load-circuit', methods=['GET', 'OPTIONS'])
def load_circuit():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        print(f"尝试加载电路数据 from: {CIRCUIT_DATA_FILE}")
        if os.path.exists(CIRCUIT_DATA_FILE):
            with open(CIRCUIT_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"电路数据已加载，包含 {len(data.get('elements', []))} 个元件")
            return jsonify(data)
        else:
            print("电路数据文件不存在，返回空数据")
            return jsonify({'elements': [], 'wires': []})
    except Exception as e:
        print(f"加载电路数据失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print(f"Flask应用启动，电路数据文件路径: {CIRCUIT_DATA_FILE}")
    app.run(debug=True, host='0.0.0.0', port=5000)
