from flask import Flask, request, jsonify, render_template, Response
import json
import os
import logging
import sys
from ai_commands import CircuitManager
import re
import requests
import time

# AI 配置 (请在此填入您的 API Key)
AI_CONFIG = {
    "api_key": "sk-38d03b2f9c8d44f886f9e146d179d933",
    "base_url": "https://api.deepseek.com", # 或者您的代理地址，例如 https://api.deepseek.com
    "model": "deepseek-chat" # 或 deepseek-chat 等
}

# 关闭Flask的HTTP请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# 获取当前文件所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 存储电路数据的文件
CIRCUIT_DATA_FILE = os.path.join(BASE_DIR, 'circuit_data.json')
# 存储函数数据的文件
FUNCTIONS_DATA_FILE = os.path.join(BASE_DIR, 'functions_data.json')

# 初始化电路管理器
circuit_manager = CircuitManager(CIRCUIT_DATA_FILE)

# 初始化：如果文件不存在，创建一个空的电路数据文件
def init_circuit_file():
    if not os.path.exists(CIRCUIT_DATA_FILE):
        try:
            with open(CIRCUIT_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'elements': [], 'wires': []}, f, indent=2, ensure_ascii=False)
            print(f"已创建空的电路数据文件: {CIRCUIT_DATA_FILE}")
        except Exception as e:
            print(f"创建电路数据文件失败: {e}")

# 初始化：如果文件不存在，创建一个空的函数数据文件
def init_functions_file():
    if not os.path.exists(FUNCTIONS_DATA_FILE):
        try:
            with open(FUNCTIONS_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'functions': []}, f, indent=2, ensure_ascii=False)
            print(f"已创建空的函数数据文件: {FUNCTIONS_DATA_FILE}")
        except Exception as e:
            print(f"创建函数数据文件失败: {e}")

# 启动时初始化
init_circuit_file()
init_functions_file()

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
        data = circuit_manager.get_state()
        print(f"电路数据已加载，包含 {len(data.get('elements', []))} 个元件")
        return jsonify(data)
    except Exception as e:
        print(f"加载电路数据失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ai/execute', methods=['POST'])
def ai_execute():
    try:
        data = request.json
        cmd = data.get('command')
        params = data.get('params', {})
        
        result = execute_circuit_command(cmd, params)
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def execute_circuit_command(cmd, params):
    """
    Helper to execute commands and return result
    """
    if cmd == 'add_element':
        return circuit_manager.add_element(params['type'], params['x'], params['y'])
    elif cmd == 'remove_element':
        return circuit_manager.remove_element(params['id'])
    elif cmd == 'add_wire':
        return circuit_manager.add_wire(params['from_id'], params['from_port_idx'], params['to_id'], params['to_port_idx'])
    elif cmd == 'remove_wire':
        return circuit_manager.remove_wire(params['id'])
    elif cmd == 'clear_circuit':
        return circuit_manager.clear_circuit()
    elif cmd == 'toggle_input':
        return circuit_manager.toggle_input(params['id'])
    elif cmd == 'get_state':
        return circuit_manager.get_state()
    else:
        raise ValueError(f'Unknown command: {cmd}')

def _parse_commands_payload(commands_str):
    content = commands_str.strip()
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()
    parsed = json.loads(content)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise ValueError("commands payload must be a JSON object or array")

def _resolve_element_ref(value, alias_map):
    if not isinstance(value, str):
        return value
    if value in alias_map:
        return alias_map[value]
    if value.startswith("$") and value[1:] in alias_map:
        return alias_map[value[1:]]
    return value

def _execute_commands_with_alias(commands):
    alias_map = {}
    last_element_id = None
    for cmd_data in commands:
        cmd = cmd_data.get('command')
        params = dict(cmd_data.get('params', {}) or {})

        if cmd == 'add_element':
            alias = params.pop('alias', None) or params.pop('ref', None) or params.pop('name', None)
            result = execute_circuit_command(cmd, params)
            if isinstance(result, dict) and result.get('id'):
                last_element_id = result['id']
                alias_map['$last'] = last_element_id
                # 即使没有显式提供 alias，我们也允许用它的 type 作为默认 alias，这样诸如 from_ref: "INPUT" 就能被解析
                # 但如果有多个同类型的，后创建的会覆盖前面的，AI如果能提供具体alias更好
                if not alias:
                    alias = params.get('type')
                if alias:
                    alias_map[alias] = last_element_id
                    alias_map[f'${alias}'] = last_element_id
            continue

        if cmd == 'add_wire':
            from_ref = params.pop('from_ref', None) or params.pop('from_alias', None)
            to_ref = params.pop('to_ref', None) or params.pop('to_alias', None)

            if from_ref and not params.get('from_id'):
                params['from_id'] = _resolve_element_ref(from_ref, alias_map)
            else:
                params['from_id'] = _resolve_element_ref(params.get('from_id'), alias_map)

            if to_ref and not params.get('to_id'):
                params['to_id'] = _resolve_element_ref(to_ref, alias_map)
            else:
                params['to_id'] = _resolve_element_ref(params.get('to_id'), alias_map)

            if params.get('from_id') == '$last' and last_element_id:
                params['from_id'] = last_element_id
            if params.get('to_id') == '$last' and last_element_id:
                params['to_id'] = last_element_id

            execute_circuit_command(cmd, params)
            continue

        execute_circuit_command(cmd, params)

def _build_compact_state(state):
    elements = state.get('elements', [])
    wires = state.get('wires', [])
    compact_elements = []
    for e in elements:
        compact_elements.append({
            'id': e.get('id'),
            'type': e.get('type'),
            'x': e.get('x'),
            'y': e.get('y'),
            'inputs': len(e.get('inputs', [])),
            'outputs': len(e.get('outputs', [])),
            'state': e.get('state', False)
        })
    compact_wires = []
    for w in wires:
        if 'start' in w and 'end' in w:
            compact_wires.append({
                'id': w.get('id'),
                'from': w.get('start', {}).get('elementId'),
                'to': w.get('end', {}).get('elementId')
            })
        elif 'from' in w and 'to' in w:
            compact_wires.append({
                'id': w.get('id'),
                'from': w.get('from', {}).get('elementId'),
                'to': w.get('to', {}).get('elementId')
            })
    return {
        'elements': compact_elements,
        'wires': compact_wires
    }

def call_llm_stream(user_message):
    """
    调用大语言模型 API，流式返回
    """
    if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        yield "请先在 app.py 中配置您的 AI_CONFIG['api_key']。"
        return

    current_state = circuit_manager.get_state()
    compact_state = _build_compact_state(current_state)
    compact_state_json = json.dumps(compact_state, ensure_ascii=False, separators=(',', ':'))
    system_prompt = """你是一个电路模拟器助手。你可以通过调用指令来操作电路。
    
可用指令集 (JSON 格式):
1. {"command": "add_element", "params": {"type": "AND|OR|NOT|INPUT|OUTPUT", "x": number, "y": number, "alias": "可选别名"}}
2. {"command": "add_wire", "params": {"from_id": string, "from_port_idx": number, "to_id": string, "to_port_idx": number}}
   或 {"command": "add_wire", "params": {"from_ref": "别名", "from_port_idx": number, "to_ref": "别名", "to_port_idx": number}}
3. {"command": "remove_element", "params": {"id": string}}
4. {"command": "clear_circuit", "params": {}}
5. {"command": "toggle_input", "params": {"id": string}}

当前电路状态:
""" + compact_state_json + """

请根据用户需求进行操作。
**回复格式要求**:
1. 先直接输出你对用户说的话（回复文字，尽量1句）。
2. 在回复的最后，用 <commands>[JSON_LIST]</commands> 标签包含你要执行的指令列表。
示例:
好的，为您添加了一个与门。<commands>[{"command": "add_element", "params": {"type": "AND", "x": 100, "y": 100}}]</commands>

注意：确保指令 JSON 格式完全正确。只在最后输出一次 <commands> 标签。
优先输出最少必要文字，避免冗长解释。"""

    try:
        response = requests.post(
            f"{AI_CONFIG['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_CONFIG['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": AI_CONFIG["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.2,
                "max_tokens": 500,
                "stream": True
            },
            timeout=30,
            stream=True
        )
        
        full_content = ""
        commands_executed = False
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_content = line_str[6:]
                    if data_content == '[DONE]':
                        break
                    
                    try:
                        chunk_json = json.loads(data_content)
                        chunk_text = chunk_json['choices'][0]['delta'].get('content', '')
                        if chunk_text:
                            full_content += chunk_text
                            
                            # 尝试实时执行指令
                            if not commands_executed and '</commands>' in full_content:
                                match = re.search(r'<commands>(.*?)</commands>', full_content, re.DOTALL)
                                if match:
                                    try:
                                        commands_str = match.group(1).strip()
                                        commands = _parse_commands_payload(commands_str)
                                        _execute_commands_with_alias(commands)
                                        commands_executed = True
                                    except Exception as e:
                                        import traceback
                                        print(f"执行流式指令失败: {e}\n{traceback.format_exc()}")
                            
                            # 实时返回文字内容给前端
                            yield chunk_text
                    except:
                        continue
        
        # 兜底：如果循环结束还没执行
        if not commands_executed:
            match = re.search(r'<commands>(.*?)</commands>', full_content, re.DOTALL)
            if match:
                try:
                    commands_str = match.group(1).strip()
                    commands = _parse_commands_payload(commands_str)
                    _execute_commands_with_alias(commands)
                except Exception as e:
                    import traceback
                    print(f"执行流式指令失败: {e}\n{traceback.format_exc()}")
                
    except Exception as e:
        yield f"调用 AI 失败: {str(e)}"

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    聊天接口：流式输出
    """
    try:
        data = request.json
        message = data.get('message', '')
        
        def generate():
            for chunk in call_llm_stream(message):
                yield chunk
                
        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def fallback_chat(message, error_msg):
    """
    回退逻辑：当 LLM 不可用时，使用关键词匹配或报错
    """
    message = message.lower()
    commands_executed = []
    reply = ""
    
    # 如果 API Key 没填，提示用户，但仍然尝试处理简单指令
    is_config_error = "YOUR_API_KEY_HERE" in error_msg
    
    if "清空" in message or "clear" in message:
        execute_circuit_command('clear_circuit', {})
        reply = "好的，我已经清空了所有电路。"
        commands_executed.append({'command': 'clear_circuit'})
    elif "与门" in message:
        res = execute_circuit_command('add_element', {'type': 'AND', 'x': 100, 'y': 100})
        reply = f"已为您添加了一个与门。"
        commands_executed.append({'command': 'add_element', 'type': 'AND'})
    else:
        if is_config_error:
            reply = "⚠️ 您尚未在 app.py 中配置 AI_CONFIG['api_key']。目前我只能处理简单的指令如“添加与门”、“清空画布”。"
        else:
            reply = f"抱歉，调用 AI 时遇到了错误: {error_msg}。"

    return jsonify({
        'status': 'success',
        'reply': reply,
        'commands_executed': commands_executed,
        'config_needed': is_config_error
    })

@app.route('/api/save-function', methods=['POST', 'OPTIONS'])
def save_function():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        new_function = request.json
        # 读取现有的函数
        functions_data = {'functions': []}
        if os.path.exists(FUNCTIONS_DATA_FILE):
            with open(FUNCTIONS_DATA_FILE, 'r', encoding='utf-8') as f:
                functions_data = json.load(f)
        
        # 添加新函数
        functions_data['functions'].append(new_function)
        
        # 写入文件
        with open(FUNCTIONS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(functions_data, f, indent=2, ensure_ascii=False)
        print(f"函数已保存到: {FUNCTIONS_DATA_FILE}")
        return jsonify({'status': 'success', 'message': 'Function saved successfully'})
    except Exception as e:
        print(f"保存函数失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save-functions', methods=['POST', 'OPTIONS'])
def save_functions():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        # 写入文件
        with open(FUNCTIONS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"函数列表已保存到: {FUNCTIONS_DATA_FILE}")
        return jsonify({'status': 'success', 'message': 'Functions saved successfully'})
    except Exception as e:
        print(f"保存函数列表失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/load-functions', methods=['GET', 'OPTIONS'])
def load_functions():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        print(f"尝试加载函数数据 from: {FUNCTIONS_DATA_FILE}")
        if os.path.exists(FUNCTIONS_DATA_FILE):
            with open(FUNCTIONS_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"函数数据已加载，包含 {len(data.get('functions', []))} 个函数")
            return jsonify(data)
        else:
            return jsonify({'functions': []})
    except Exception as e:
        print(f"加载函数数据失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print(f"电路设计应用启动中...")
    print(f"电路数据文件路径: {CIRCUIT_DATA_FILE}")
    print(f"函数数据文件路径: {FUNCTIONS_DATA_FILE}")
    print(f"打开软件: http://localhost:5000")
    # 禁用Flask的开发服务器banner
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    app.run(debug=False, host='0.0.0.0', port=5000)
