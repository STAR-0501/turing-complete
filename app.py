from flask import Flask, request, jsonify, render_template, Response
import glob
import json
import os
import logging
import sys
from ai_commands import CircuitManager
import re
import requests
import tempfile
import time
import threading

# AI 配置 (请在此填入您的 API Key)
AI_CONFIG = {
    "api_key": "sk-38d03b2f9c8d44f886f9e146d179d933",
    "base_url": "https://api.deepseek.com", # 或者您的代理地址，例如 https://api.deepseek.com
    "model": "deepseek-v4-flash" # 或 deepseek-chat 等
}

# 关闭Flask的HTTP请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

app = Flask(__name__)

CHAT_MEMORY_MAX_MESSAGES = 12
CHAT_MESSAGE_MAX_CHARS = 1500
STREAM_THINKING_MARKER = "__TC_THINKING__"
STREAM_ANSWER_MARKER = "__TC_ANSWER__"
STREAM_STATE_CHANGED_MARKER = "__TC_STATE_CHANGED__"
chat_memory = []
chat_memory_lock = threading.Lock()

# 获取当前文件所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 存储电路数据的文件
CIRCUIT_DATA_FILE = os.path.join(BASE_DIR, 'circuit_data.json')
# 存储函数数据的文件
FUNCTIONS_DATA_FILE = os.path.join(BASE_DIR, 'functions_data.json')

# 初始化电路管理器
circuit_manager = CircuitManager(CIRCUIT_DATA_FILE, FUNCTIONS_DATA_FILE)

# 初始化：如果文件不存在，创建一个空的电路数据文件
def init_circuit_file():
    if not os.path.exists(CIRCUIT_DATA_FILE):
        try:
            with open(CIRCUIT_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'elements': [], 'wires': []}, f, indent=2, ensure_ascii=False)
            logger.info("已创建空的电路数据文件: %s", CIRCUIT_DATA_FILE)
        except Exception as e:
            logger.error("创建电路数据文件失败: %s", e)

# 初始化：如果文件不存在，创建一个空的函数数据文件
def init_functions_file():
    if not os.path.exists(FUNCTIONS_DATA_FILE):
        try:
            with open(FUNCTIONS_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'functions': []}, f, indent=2, ensure_ascii=False)
            logger.info("已创建空的函数数据文件: %s", FUNCTIONS_DATA_FILE)
        except Exception as e:
            logger.error("创建函数数据文件失败: %s", e)

# 启动时初始化
init_circuit_file()
init_functions_file()

def _atomic_write_json(path, data):
    for stale in glob.glob(f"{path}.tmp.*"):
        try:
            os.remove(stale)
        except OSError:
            pass
    dir_name = os.path.dirname(path) or os.getcwd()
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=dir_name, prefix=f".{os.path.basename(path)}.tmp.",
        delete=False
    ) as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        tmp_path = f.name
    try:
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

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
        _atomic_write_json(CIRCUIT_DATA_FILE, data)
        logger.info("电路数据已保存到: %s", CIRCUIT_DATA_FILE)
        return jsonify({'status': 'success', 'message': 'Circuit saved successfully'})
    except Exception as e:
        logger.error("保存电路数据失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/load-circuit', methods=['GET', 'OPTIONS'])
def load_circuit():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = circuit_manager.get_state()
        logger.info("电路数据已加载，包含 %d 个元件", len(data.get('elements', [])))
        return jsonify(data)
    except Exception as e:
        logger.error("加载电路数据失败: %s", e)
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

@app.route('/api/ai/generate-comments', methods=['POST'])
def ai_generate_comments():
    try:
        if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
            return jsonify({'status': 'error', 'message': '请先在 app.py 中配置 AI_CONFIG[api_key]'}), 400
        
        current_state = circuit_manager.get_state()
        elements = current_state.get('elements', [])
        wires = current_state.get('wires', [])
        
        if not elements:
            return jsonify({'status': 'success', 'comments': {}})
        
        system_prompt = """你是一个电路分析专家。请分析下面的电路，为每个元件生成精准的注释，说明它在电路中的作用和功能。

要求：
1. 注释要简洁明了，不超过30个字
2. 说明元件的具体功能，如"A输入：电路的第一个操作数"
3. 如果是门电路，说明它的逻辑功能
4. 如果是输出，说明它代表什么结果

请以 JSON 格式输出，key 是元件 id，value 是注释内容。
格式：{"元件id": "注释内容", ...}
只输出 JSON，不要其他内容。"""

        elements_info = []
        for el in elements:
            el_info = {
                "id": el.get("id"),
                "type": el.get("type"),
                "alias": el.get("alias"),
                "state": el.get("state"),
                "functionName": el.get("name") if el.get("type") == "FUNCTION" else None
            }
            elements_info.append(el_info)
        
        wires_info = []
        for w in wires:
            start_el = next((e for e in elements if e.get("id") == w.get("start", {}).get("elementId")), None)
            end_el = next((e for e in elements if e.get("id") == w.get("end", {}).get("elementId")), None)
            wires_info.append({
                "from": f"{start_el.get('type')}" if start_el else "unknown",
                "to": f"{end_el.get('type')}" if end_el else "unknown"
            })
        
        user_prompt = f"""电路中的元件：
{json.dumps(elements_info, ensure_ascii=False, indent=2)}

电路连接关系：
{json.dumps(wires_info, ensure_ascii=False, indent=2)}

请分析这个电路，为每个元件生成注释："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = requests.post(
            f"{AI_CONFIG['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_CONFIG['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": AI_CONFIG.get("model", "default"),
                "messages": messages,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code != 200:
            return jsonify({'status': 'error', 'message': f'AI API 错误: {response.text}'}), 500
        
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            comments = json.loads(json_match.group())
        else:
            comments = {}
        
        for el in elements:
            el_id = el.get("id")
            if el_id in comments:
                el["comment"] = comments[el_id]
        
        circuit_manager._save_data(current_state)
        
        return jsonify({'status': 'success', 'comments': comments})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ai/generate-layout', methods=['POST'])
def ai_generate_layout():
    """
    根据当前电路结构，让AI整理布局
    """
    try:
        if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
            return jsonify({'status': 'error', 'message': '请先在 app.py 中配置 AI_CONFIG[api_key]'}), 400
        
        current_state = circuit_manager.get_state()
        elements = current_state.get('elements', [])
        wires = current_state.get('wires', [])
        
        if not elements:
            return jsonify({'status': 'success', 'positions': {}})
        
        system_prompt = """请整理这个电路
        要求：
        1.尽可能保持正方形，不是一直向下或者向右；
        2.尽可能体现这个电路的功能，让人一眼能看懂电路，符合人的阅读习惯；
        3.如果是二进制数字，应当保证把高位到低位按照从左到右的顺序排，比如一个三位数，用了三个输入（或者输出）模块，那么最高位应当在最左边，最低为应当在最右边，不论是输入还是输出，都必须按这个要求排列，不能从上到下排。
        """

        elements_info = []
        for el in elements:
            el_info = {
                "id": el.get("id"),
                "type": el.get("type"),
                "alias": el.get("alias"),
                "comment": el.get("comment", ""),
                "current_x": el.get("x"),
                "current_y": el.get("y"),
                "width": el.get("width", 80),
                "height": el.get("height", 60)
            }
            elements_info.append(el_info)
        
        wires_info = []
        for w in wires:
            start_el = next((e for e in elements if e.get("id") == w.get("start", {}).get("elementId")), None)
            end_el = next((e for e in elements if e.get("id") == w.get("end", {}).get("elementId")), None)
            wires_info.append({
                "from": f"{start_el.get('type')}" if start_el else "unknown",
                "to": f"{end_el.get('type')}" if end_el else "unknown"
            })
        
        user_prompt = f"""电路中的元件：
{json.dumps(elements_info, ensure_ascii=False, indent=2)}

电路连接关系：
{json.dumps(wires_info, ensure_ascii=False, indent=2)}

请设计合理的布局方案并输出MOVE命令："""

        user_message = f"{system_prompt}\n\n{user_prompt}"
        
        def generate():
            try:
                for chunk in call_llm_stream(user_message, max_rounds_override=2):
                    yield chunk
            except Exception as e:
                yield f"\n整理电路时出错: {str(e)}"
        
        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ai/generate-circuit', methods=['POST'])
def ai_generate_circuit():
    """
    根据用户需求生成电路
    """
    try:
        if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
            return jsonify({'status': 'error', 'message': '请先在 app.py 中配置 AI_CONFIG[api_key]'}), 400
        
        data = request.json
        user_requirement = data.get('requirement', '')
        
        if not user_requirement:
            return jsonify({'status': 'error', 'message': '请提供电路需求描述'}), 400
        
        def generate():
            try:
                for chunk in call_llm_stream(user_requirement):
                    yield chunk
            except Exception as e:
                yield f"\n生成电路时出错: {str(e)}"
        
        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def execute_circuit_command(cmd, params):
    """
    Helper to execute commands and return result
    """
    if cmd == 'add_element':
        return circuit_manager.add_element(params['type'], params['x'], params['y'], params.get('alias'))
    elif cmd == 'remove_element':
        return circuit_manager.remove_element(params['id'])
    elif cmd == 'add_wire':
        return circuit_manager.add_wire(params['from_id'], params['from_port_idx'], params['to_id'], params['to_port_idx'])
    elif cmd == 'remove_wire':
        return circuit_manager.remove_wire(params['id'])
    elif cmd == 'clear_circuit':
        return circuit_manager.clear_circuit()
    elif cmd == 'define_function':
        return circuit_manager.define_function(params['name'])
    elif cmd == 'toggle_input':
        return circuit_manager.toggle_input(params['id'])
    elif cmd == 'set_input':
        return circuit_manager.set_input(params['id'], params.get('value'))
    elif cmd == 'move_element':
        return circuit_manager.move_element(params['id'], params['x'], params['y'])
    elif cmd == 'set_element_comment':
        return circuit_manager.set_element_comment(params['id'], params.get('comment', ''))
    elif cmd == 'get_state':
        return circuit_manager.get_state()
    elif cmd == 'simulate':
        return circuit_manager.simulate()
    elif cmd == 'sample_outputs':
        return circuit_manager.sample_outputs(params.get('ids'))
    else:
        raise ValueError(f'Unknown command: {cmd}')

def _parse_commands_payload(commands_str):
    content = commands_str.strip()
    if content.startswith("```"):
        content = re.sub(r'^```[a-zA-Z]*\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()

    def _clean_token(token):
        if not isinstance(token, str):
            return token
        return token.strip().strip('`').strip(',;，；。')

    def _parse_bool_token(token):
        if token is None:
            return None
        t = str(token).strip().lower()
        if t in {"1", "true", "yes", "on"}:
            return True
        if t in {"0", "false", "no", "off"}:
            return False
        return None

    commands = []
    for line in content.split('\n'):
        line = line.strip()
        line = re.sub(r'^\s*[-*]\s*', '', line)
        line = re.sub(r'^\s*\d+[\.\)]\s*', '', line)
        if not line or line.startswith('#'):
            continue
        parts = [_clean_token(p) for p in line.split() if _clean_token(p)]
        if not parts:
            continue

        cmd = _clean_token(parts[0]).upper()

        try:
            if cmd == 'ADD':
                if len(parts) >= 4:
                    element_type = _clean_token(parts[1]).upper()
                    # We remove the strict type check here to allow custom function names
                    # Or check if it's in the allowed basic types OR let CircuitManager handle it
                    params = {
                        'type': element_type if element_type in {'AND', 'OR', 'NOT', 'INPUT', 'OUTPUT'} else _clean_token(parts[1]),
                        'x': float(_clean_token(parts[2])),
                        'y': float(_clean_token(parts[3]))
                    }
                    if len(parts) >= 5:
                        params['alias'] = _clean_token(parts[4])
                    commands.append({'command': 'add_element', 'params': params})
            elif cmd == 'WIRE':
                if len(parts) >= 5:
                    commands.append({
                        'command': 'add_wire',
                        'params': {
                            'from_ref': _clean_token(parts[1]),
                            'from_port_idx': int(float(_clean_token(parts[2]))),
                            'to_ref': _clean_token(parts[3]),
                            'to_port_idx': int(float(_clean_token(parts[4])))
                        }
                    })
            elif cmd == 'DEL':
                if len(parts) >= 2:
                    commands.append({'command': 'remove_element', 'params': {'id': _clean_token(parts[1])}})
            elif cmd == 'DELW':
                if len(parts) >= 2:
                    commands.append({'command': 'remove_wire', 'params': {'id': _clean_token(parts[1])}})
            elif cmd == 'CLEAR':
                commands.append({'command': 'clear_circuit', 'params': {}})
            elif cmd == 'DEFINE_FUNC':
                if len(parts) >= 2:
                    commands.append({'command': 'define_function', 'params': {'name': _clean_token(parts[1])}})
            elif cmd == 'TOGGLE':
                if len(parts) >= 2:
                    commands.append({'command': 'toggle_input', 'params': {'id': _clean_token(parts[1])}})
            elif cmd == 'SET':
                if len(parts) >= 3:
                    v = _parse_bool_token(parts[2])
                    if v is not None:
                        commands.append({'command': 'set_input', 'params': {'id': _clean_token(parts[1]), 'value': v}})
            elif cmd in ('SIM', 'SIMULATE'):
                commands.append({'command': 'simulate', 'params': {}})
            elif cmd == 'SAMPLE':
                ids = [_clean_token(p) for p in parts[1:]] if len(parts) > 1 else []
                params = {'ids': ids} if ids else {}
                commands.append({'command': 'sample_outputs', 'params': params})
            elif cmd == 'MOVE':
                if len(parts) >= 4:
                    commands.append({
                        'command': 'move_element',
                        'params': {
                            'id': _clean_token(parts[1]),
                            'x': float(_clean_token(parts[2])),
                            'y': float(_clean_token(parts[3]))
                        }
                    })
            elif cmd == 'COMMENT':
                if len(parts) >= 3:
                    comment_text = ' '.join(parts[2:]).replace('\\n', '\n')
                    commands.append({
                        'command': 'set_element_comment',
                        'params': {
                            'id': _clean_token(parts[1]),
                            'comment': comment_text
                        }
                    })
        except:
            continue

    return commands

def _resolve_element_ref(value, alias_map):
    if not isinstance(value, str):
        return value
    value = value.strip()
    if value in alias_map:
        return alias_map[value]
    if value.upper() in alias_map:
        return alias_map[value.upper()]
    if value.lower() in alias_map:
        return alias_map[value.lower()]
    if value.startswith("$") and value[1:] in alias_map:
        return alias_map[value[1:]]
    return value

def _execute_commands_with_alias(commands):
    alias_map = {}
    last_element_id = None
    pending_wires = []
    errors = []
    results = []
    executed_success = 0

    def _bind_alias(alias, element_id):
        if not alias:
            return
        alias_map[alias] = element_id
        alias_map[f'${alias}'] = element_id
        alias_map[alias.upper()] = element_id
        alias_map[f'${alias.upper()}'] = element_id
        alias_map[alias.lower()] = element_id
        alias_map[f'${alias.lower()}'] = element_id

    try:
        state = circuit_manager.get_state() or {}
        for el in (state.get('elements') or []):
            alias = el.get('alias')
            el_id = el.get('id')
            if alias and el_id:
                _bind_alias(alias, el_id)
    except:
        pass

    def _try_execute_wire(raw_params):
        params = dict(raw_params or {})
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

        execute_circuit_command('add_wire', params)

    def _flush_pending_wires():
        nonlocal pending_wires
        retries = 3
        last_failures = []
        for _ in range(retries):
            if not pending_wires:
                break
            unresolved_wires = []
            failures = []
            executed_count = 0
            for wire_params in pending_wires:
                try:
                    _try_execute_wire(wire_params)
                    executed_count += 1
                    results.append({"command": "add_wire", "result": "ok"})
                except Exception as e:
                    failures.append(str(e))
                    unresolved_wires.append(wire_params)
            pending_wires = unresolved_wires
            last_failures = failures
            if executed_count == 0:
                break
        if pending_wires:
            for idx, wire_params in enumerate(pending_wires):
                msg = last_failures[idx] if idx < len(last_failures) else "无法连接导线"
                errors.append({"command": "add_wire", "error": msg, "params": wire_params})
            pending_wires = []

    for cmd_data in commands:
        cmd = cmd_data.get('command')
        params = dict(cmd_data.get('params', {}) or {})

        if cmd == 'add_element':
            specified_alias = params.pop('alias', None) or params.pop('ref', None) or params.pop('name', None)
            alias = specified_alias
            try:
                if specified_alias:
                    params['alias'] = specified_alias
                result = execute_circuit_command(cmd, params)
                executed_success += 1
                results.append({"command": "add_element", "result": {"id": result.get("id")} if isinstance(result, dict) else "ok"})
            except Exception as e:
                errors.append({"command": "add_element", "error": str(e), "params": params})
                continue
            if isinstance(result, dict) and result.get('id'):
                last_element_id = result['id']
                alias_map['$last'] = last_element_id
                if not alias:
                    alias = params.get('type')
                _bind_alias(alias, last_element_id)
            continue

        if cmd == 'add_wire':
            pending_wires.append(params)
            continue

        if 'id' in params:
            params['id'] = _resolve_element_ref(params['id'], alias_map)
            if params['id'] == '$last' and last_element_id:
                params['id'] = last_element_id
        if 'ids' in params and isinstance(params.get('ids'), list):
            params['ids'] = [_resolve_element_ref(v, alias_map) for v in params.get('ids') if v is not None]

        if cmd in ('clear_circuit', 'define_function', 'remove_element', 'remove_wire'):
            _flush_pending_wires()

        try:
            result = execute_circuit_command(cmd, params)
            executed_success += 1
            if cmd in ("sample_outputs",):
                results.append({"command": cmd, "result": result})
            else:
                results.append({"command": cmd, "result": "ok"})
        except Exception as e:
            errors.append({"command": cmd, "error": str(e), "params": params})
            continue

    _flush_pending_wires()
    try:
        circuit_manager.simulate()
    except Exception as e:
        errors.append({"command": "simulate", "error": str(e)})

    return {"executed_success": executed_success, "errors": errors, "results": results}

def _build_compact_state(state):
    elements = state.get('elements', [])
    wires = state.get('wires', [])
    compact_elements = []
    for e in elements:
        compact_elements.append({
            'id': e.get('id'),
            'type': e.get('type'),
            'alias': e.get('alias') or e.get('name'),
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

def _build_io_summary(state):
    elements = (state or {}).get("elements") or []
    inputs = []
    outputs = []
    for e in elements:
        t = e.get("type")
        if t == "INPUT":
            inputs.append({"id": e.get("id"), "alias": e.get("alias") or e.get("name"), "state": bool(e.get("state", False))})
        elif t == "OUTPUT":
            outputs.append({"id": e.get("id"), "alias": e.get("alias") or e.get("name"), "state": bool(e.get("state", False))})
    return {"inputs": inputs, "outputs": outputs}

def _strip_commands_from_reply(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r'<commands>[\s\S]*?(</commands>|$)', '', text, flags=re.DOTALL).strip()

def _normalize_memory_text(text):
    if not isinstance(text, str):
        return ""
    return text.strip()[:CHAT_MESSAGE_MAX_CHARS]

def _get_chat_messages_with_memory(user_message):
    with chat_memory_lock:
        messages = list(chat_memory)
    messages.append({"role": "user", "content": _normalize_memory_text(user_message)})
    return messages

def _append_chat_memory(role, content):
    normalized = _normalize_memory_text(content)
    if not normalized:
        return
    with chat_memory_lock:
        chat_memory.append({"role": role, "content": normalized})
        if len(chat_memory) > CHAT_MEMORY_MAX_MESSAGES:
            overflow = len(chat_memory) - CHAT_MEMORY_MAX_MESSAGES
            del chat_memory[:overflow]

def _get_ai_protocol():
    protocol = str(AI_CONFIG.get("protocol", "")).strip().lower()
    if protocol:
        return protocol
    base_url = str(AI_CONFIG.get("base_url", "")).lower()
    if "/anthropic" in base_url:
        return "anthropic"
    return "openai"

def _extract_chunk_parts(chunk_json, protocol):
    if not isinstance(chunk_json, dict):
        return "", ""

    if protocol == "anthropic":
        chunk_type = chunk_json.get("type")
        if chunk_type == "content_block_delta":
            delta = chunk_json.get("delta") or {}
            if delta.get("type") == "thinking_delta":
                return "", delta.get("thinking", "") or ""
            return delta.get("text", "") or "", ""
        if chunk_type == "content_block_start":
            block = chunk_json.get("content_block") or {}
            if block.get("type") == "text":
                return block.get("text", "") or "", ""
            if block.get("type") == "thinking":
                return "", block.get("thinking", "") or ""
        if chunk_type == "message_start":
            message = chunk_json.get("message") or {}
            content = message.get("content") or []
            if content and isinstance(content, list):
                first = content[0] or {}
                if first.get("type") == "text":
                    return first.get("text", "") or "", ""
                if first.get("type") == "thinking":
                    return "", first.get("thinking", "") or ""
        return "", ""

    choices = chunk_json.get('choices') or []
    if choices and isinstance(choices, list):
        delta = choices[0].get('delta') or {}
        reasoning = delta.get('reasoning') or delta.get('reasoning_content')
        if isinstance(reasoning, str) and reasoning:
            return "", reasoning
        if isinstance(reasoning, list):
            thinking_text = ''.join(
                part.get('text', '') for part in reasoning if isinstance(part, dict)
            )
            if thinking_text:
                return "", thinking_text
        content = delta.get('content', '')
        if isinstance(content, str):
            return content, ""

    delta = chunk_json.get("delta") or {}
    if isinstance(delta, dict):
        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            return "", reasoning
        text = delta.get("text") or delta.get("content")
        if isinstance(text, str):
            return text, ""

    content = chunk_json.get("content")
    if isinstance(content, str):
        return content, ""
    return "", ""

def _extract_finish_reason(chunk_json, protocol):
    if not isinstance(chunk_json, dict):
        return ""

    if protocol == "anthropic":
        if chunk_json.get("type") == "message_delta":
            delta = chunk_json.get("delta") or {}
            return str(delta.get("stop_reason") or "")
        return ""

    choices = chunk_json.get("choices") or []
    if choices and isinstance(choices, list):
        return str(choices[0].get("finish_reason") or "")
    return ""

def _extract_tag_text(text, tag):
    if not isinstance(text, str):
        return ""
    pattern = rf'<{tag}>([\s\S]*?)</{tag}>'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _extract_verify_payload(text):
    payload = _extract_tag_text(text, "verify")
    if not payload:
        return None
    try:
        return json.loads(payload)
    except:
        return None

def _resolve_ref_to_id(value, state):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    v = value.strip()
    if not v:
        return v
    elements = (state or {}).get("elements") or []
    for el in elements:
        if el.get("id") == v:
            return v
    for el in elements:
        if (el.get("alias") or "").strip() == v:
            return el.get("id")
    if v.startswith("$"):
        raw = v[1:]
        for el in elements:
            if (el.get("alias") or "").strip() == raw:
                return el.get("id")
    return v

def _run_verify_cases(verify_obj):
    if not isinstance(verify_obj, dict):
        return None
    cases = verify_obj.get("cases")
    if cases is None:
        single = {"inputs": verify_obj.get("inputs") or [], "expect": verify_obj.get("expect") or []}
        cases = [single]
    if not isinstance(cases, list) or not cases:
        return None

    max_cases = 16
    cases = cases[:max_cases]

    report = {"total": len(cases), "passed": 0, "failed": 0, "cases": []}
    for idx, case in enumerate(cases, start=1):
        inputs = (case or {}).get("inputs") or []
        expect = (case or {}).get("expect") or []
        case_result = {"index": idx, "pass": True, "details": []}
        try:
            state = circuit_manager.get_state()
            for inp in inputs:
                ref = (inp or {}).get("id")
                val = (inp or {}).get("value")
                el_id = _resolve_ref_to_id(ref, state)
                circuit_manager.set_input(el_id, bool(val))
            circuit_manager.simulate()
            out_sample = circuit_manager.sample_outputs(None)
            out_map = {}
            for o in (out_sample.get("outputs") or []):
                out_map[o.get("id")] = bool(o.get("state", False))
                if o.get("alias"):
                    out_map[o.get("alias")] = bool(o.get("state", False))

            for exp in expect:
                ref = (exp or {}).get("id")
                want = bool((exp or {}).get("value"))
                got = out_map.get(ref)
                if got is None:
                    el_id = _resolve_ref_to_id(ref, state)
                    got = out_map.get(el_id)
                ok = (got is not None and bool(got) == want)
                if not ok:
                    case_result["pass"] = False
                case_result["details"].append({"id": ref, "want": want, "got": got, "ok": ok})
        except Exception as e:
            case_result["pass"] = False
            case_result["details"].append({"error": str(e)})

        if case_result["pass"]:
            report["passed"] += 1
        else:
            report["failed"] += 1
        report["cases"].append(case_result)

    return report

def _extract_commands_block(text):
    if not isinstance(text, str):
        return ""
    matches = re.findall(r'<commands>([\s\S]*?)</commands>', text, re.IGNORECASE)
    if matches:
        merged = "\n".join([m.strip() for m in matches if m and m.strip()]).strip()
        return merged
    open_match = re.search(r'<commands>([\s\S]*)', text, re.IGNORECASE)
    if open_match:
        return open_match.group(1).strip()
    return ""

def _is_done_response(text):
    done_text = _extract_tag_text(text, "done").lower()
    return done_text in {"true", "yes", "1", "done"}

def _extract_answer_text(text):
    answer = _extract_tag_text(text, "answer")
    if answer:
        return answer
    stripped = re.sub(r'<plan>[\s\S]*?</plan>', '', text, flags=re.IGNORECASE).strip()
    stripped = re.sub(r'<done>[\s\S]*?</done>', '', stripped, flags=re.IGNORECASE).strip()
    stripped = _strip_commands_from_reply(stripped)
    return stripped

def _build_autonomous_system_prompt(compact_state_json, functions_str):
    return """你是一个电路模拟器自治执行助手。你不仅要生成指令，还要在每轮执行后检查结果并决定是否继续整改。

可用指令集 (每行一条):
1. ADD <type> <x> <y> [alias]  -- 添加元件 (AND|OR|NOT|INPUT|OUTPUT 或自定义函数)
2. WIRE <from_id_or_alias> <from_port_idx> <to_id_or_alias> <to_port_idx> -- 连接导线
3. MOVE <id_or_alias> <x> <y> -- 移动元件位置
4. DEL <id_or_alias> -- 删除元件
5. DELW <wire_id> -- 删除导线
6. CLEAR -- 清空画布
7. TOGGLE <id_or_alias> -- 切换输入状态 (用于测试)
8. DEFINE_FUNC <name> -- 将当前电路封装为函数
9. SET <id_or_alias> <0|1> -- 将 INPUT 设置为指定电平（用于确定性测试）
10. SIM -- 显式触发仿真
11. SAMPLE [id_or_alias ...] -- 采样输出端口状态（默认采样全部 OUTPUT）
12. COMMENT <id_or_alias> <text> -- 设置元件的注释（text 可以包含换行，使用 \n 表示换行）

逻辑参考 (标准门实现):
- NAND(A, B): NOT(AND(A, B))
- NOR(A, B): NOT(OR(A, B))
- XOR(A, B): OR(AND(A, NOT(B)), AND(NOT(A), B))
- HalfAdder(A, B): SUM = XOR(A, B), CARRY = AND(A, B)

规则:
- 基础门只允许 AND、OR、NOT、INPUT、OUTPUT。严禁直接使用 XOR 等。
- 必须使用函数思维：复杂逻辑先搭建 -> DEFINE_FUNC -> SET+SAMPLE 验证 -> 通过后 CLEAR -> ADD <函数名> 复用。DEFINE_FUNC 后未经验证就 CLEAR 视为错误。
- 每轮最多输出 30 条命令。如果目标需要超过 30 条命令，分多轮完成，每轮完成后先验证再继续。
- 坐标规则：不要手动为每个元件算精确坐标，使用"基准坐标 + 相对偏移"策略。
  - 输入：x 固定 80，y 从 60 开始递增 80（60, 140, 220, 300...）
  - 门电路：x 固定 240，y 与对应输入的 y 对齐
  - 输出：x 固定 560，y 与对应信号的 y 对齐
  - 同一类元件的 y 间距固定为 80，确保不会重叠
- 验证驱动：用 SET 做确定性输入，然后用 SAMPLE 查看 OUTPUT 结果来验证，再决定 done。
- 强烈建议：给关键元件设置 alias（ADD 第 5 个参数）。alias 会持久化，后续所有 <id_or_alias> 都可以直接使用 alias。
- 先想后做：在输出命令前，先明确目标、关键假设与下一步；如果目标不清晰或存在多种解释，在 <answer> 里说明并提出最小化的下一步验证/操作。
- 简单优先：用最少的元件与最少的命令达成目标；不要为了"看起来更好"进行无关重搭或大规模重排，除非用户明确要求。
- 手术式修改：只改为完成当前目标必须改的部分；不要顺手重构/重命名/清理无关线路；如果发现无关问题，在 <answer> 提醒但不要擅自处理。
- 目标驱动验证：每完成一个关键子目标就用 SET+SAMPLE 或 <verify> 跑用例确认；验证失败则解释差异并继续整改。
- done 的标准：只有当你已经用 state（必要时用 TOGGLE 做测试）验证目标达成，且不需要再执行任何命令时，才输出 done=true。
- 如果用户目标需要改动画布，但你在本轮没有输出任何可执行命令，则 done 必须为 false，并给出下一步命令或说明阻碍点。

当前函数信息:
""" + functions_str + """

当前电路状态 (含实时逻辑电平 state):
""" + compact_state_json + """

你必须严格输出以下结构:
<plan>
不超过 80 字，只写"本轮做什么 + 坐标策略"。不需要解释逻辑门原理、不需要推导真值表、不需要讨论可不用的方案。
</plan>
<answer>
给用户的简短说明
</answer>
<commands>
命令列表
</commands>
<verify>
可选：用 JSON 描述测试用例。示例：
{"cases":[{"inputs":[{"id":"A","value":0},{"id":"B","value":1}],"expect":[{"id":"SUM","value":1},{"id":"CARRY","value":0}]}]}
</verify>
<done>true 或 false</done>

当你确认电路逻辑正确（通过 state 验证）且布局合理时，done 设为 true。"""

def _call_llm_once(system_prompt, request_messages):
    protocol = _get_ai_protocol()
    base_url = str(AI_CONFIG['base_url']).rstrip('/')
    if protocol == "anthropic":
        request_url = f"{base_url}/v1/messages"
        request_headers = {
            "x-api-key": AI_CONFIG['api_key'],
            "anthropic-version": AI_CONFIG.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": AI_CONFIG["model"],
            "system": system_prompt,
            "messages": request_messages,
            "temperature": 0.2,
            "max_tokens": int(AI_CONFIG.get("max_tokens", 4000)),
            "stream": False
        }
    else:
        request_url = f"{base_url}/chat/completions"
        request_headers = {
            "Authorization": f"Bearer {AI_CONFIG['api_key']}",
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": AI_CONFIG["model"],
            "messages": [{"role": "system", "content": system_prompt}] + request_messages,
            "temperature": 0.2,
            "max_tokens": int(AI_CONFIG.get("max_tokens", 4000)),
            "stream": False
        }
    connect_timeout = float(AI_CONFIG.get("connect_timeout", 10))
    read_timeout = float(AI_CONFIG.get("read_timeout", 180))
    response = requests.post(
        request_url,
        headers=request_headers,
        json=request_payload,
        timeout=(connect_timeout, read_timeout)
    )
    response.raise_for_status()
    payload = response.json()
    if protocol == "anthropic":
        content = payload.get("content") or []
        text = ''.join([c.get("text", "") for c in content if isinstance(c, dict)])
        finish_reason = str(payload.get("stop_reason") or "")
        return text, finish_reason
    choices = payload.get("choices") or []
    if not choices:
        return "", ""
    message = choices[0].get("message") or {}
    finish_reason = str(choices[0].get("finish_reason") or "")
    return str(message.get("content") or ""), finish_reason

def _call_llm_streaming(system_prompt, request_messages, thinking_mode=False):
    protocol = _get_ai_protocol()
    base_url = str(AI_CONFIG['base_url']).rstrip('/')
    if protocol == "anthropic":
        request_url = f"{base_url}/v1/messages"
        request_headers = {
            "x-api-key": AI_CONFIG['api_key'],
            "anthropic-version": AI_CONFIG.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": AI_CONFIG["model"],
            "system": system_prompt,
            "messages": request_messages,
            "temperature": 0.2,
            "max_tokens": int(AI_CONFIG.get("max_tokens", 4000)),
            "stream": True
        }
    else:
        request_url = f"{base_url}/chat/completions"
        request_headers = {
            "Authorization": f"Bearer {AI_CONFIG['api_key']}",
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": AI_CONFIG["model"],
            "messages": [{"role": "system", "content": system_prompt}] + request_messages,
            "max_tokens": int(AI_CONFIG.get("max_tokens", 4000)),
            "stream": True
        }
        if thinking_mode:
            request_payload["reasoning_effort"] = "high"
            request_payload["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            request_payload["temperature"] = 0.2

    connect_timeout = float(AI_CONFIG.get("connect_timeout", 10))
    read_timeout = float(AI_CONFIG.get("read_timeout", 180))
    resp = requests.post(
        request_url,
        headers=request_headers,
        json=request_payload,
        stream=True,
        timeout=(connect_timeout, read_timeout)
    )
    resp.raise_for_status()

    finish_reason = ""
    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.strip()
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if not line or line == "[DONE]":
            continue
        try:
            chunk_json = json.loads(line)
        except json.JSONDecodeError:
            continue
        text_part, thinking_part = _extract_chunk_parts(chunk_json, protocol)
        fr = _extract_finish_reason(chunk_json, protocol)
        if fr:
            finish_reason = fr
        if thinking_part:
            yield thinking_part, finish_reason
        if text_part:
            yield text_part, finish_reason

def _quick_classify(user_message):
    """Quickly determine if user wants circuit work or just casual chat."""
    compact_state = circuit_manager.get_state()
    compact_json = json.dumps(_build_compact_state(compact_state), ensure_ascii=False, separators=(',', ':'))
    sys_prompt = (
        "你是一个电路设计助手。根据用户的输入和当前电路状态，判断用户是:\n"
        "1. 需要构建/修改/验证电路 → 模式 circuit\n"
        "2. 只是日常聊天、打招呼、提问（不需要改动画布） → 模式 chat\n\n"
        f"当前电路: {compact_json}\n\n"
        "仅输出一行JSON: {\"mode\": \"circuit\" 或 \"chat\"}"
    )
    messages = [{"role": "user", "content": user_message}]
    try:
        text, _ = _call_llm_once(sys_prompt, messages)
    except requests.ConnectionError as e:
        logger.warning("分类请求网络连接失败，默认走 circuit 模式: %s", e)
        return "circuit"
    except requests.Timeout as e:
        logger.warning("分类请求超时，默认走 circuit 模式: %s", e)
        return "circuit"
    except requests.HTTPError as e:
        logger.warning("分类请求 API 错误 (HTTP %s)，默认走 circuit 模式", e.response.status_code if e.response else "?")
        return "circuit"
    except Exception as e:
        logger.warning("分类请求发生未知异常 (%s: %s)，默认走 circuit 模式", type(e).__name__, e)
        return "circuit"

    if not text or not text.strip():
        logger.warning("分类请求返回空内容，默认走 circuit 模式")
        return "circuit"

    try:
        text = text.strip()
        json_start = text.index('{')
        json_end = text.rindex('}') + 1
        parsed = json.loads(text[json_start:json_end])
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("分类响应 JSON 解析失败 (%s)，原始响应: %.100s", e, text.replace('\n', ' '))
        safe = user_message.strip().lower()
        circuit_keywords = ["add", "wire", "del", "move", "clear", "toggle", "set", "sim", "sample",
                            "define_func", "comment", "and", "or", "not", "input", "output",
                            "搭", "放", "做", "加", "连接", "删除", "移动", "清空", "验证",
                            "电路", "门", "仿真", "测试", "乘法", "加法", "函数"]
        has_circuit_intent = any(kw in safe for kw in circuit_keywords)
        has_chat_intent = any(kw in safe for kw in ["你好", "嗨", "早上好", "晚上好", "谢谢", "再见",
                                                      "你是谁", "能做什么", "hello", "hi"])
        if has_circuit_intent:
            return "circuit"
        if has_chat_intent or len(safe) < 10:
            return "chat"
        return "chat"

    mode = parsed.get("mode", "circuit")
    if mode not in ("circuit", "chat"):
        logger.warning("分类响应 mode 值异常: %s，默认走 circuit", mode)
        return "circuit"
    return mode

def call_llm_stream(user_message, max_rounds_override=None, thinking_mode=False):
    if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        yield "请先在 app.py 中配置您的 AI_CONFIG['api_key']。"
        return

    mode = _quick_classify(user_message)
    logger.info("用户消息分类: %s", mode)

    if mode == "chat":
        compact_state = circuit_manager.get_state()
        compact_json = json.dumps(_build_compact_state(compact_state), ensure_ascii=False, separators=(',', ':'))
        sys_prompt = (
            "你是一个电路设计助手。用中文友好、简洁地回答用户。"
            "不需要输出任何指令或特殊格式。"
            "如果用户问关于当前电路的问题，可以参考以下状态回答：\n"
            f"{compact_json}"
        )
        request_messages = _get_chat_messages_with_memory(user_message)
        text, fr = _call_llm_once(sys_prompt, request_messages)
        response_text = text if text else "(无法获取回答)"
        for line in response_text.splitlines():
            yield line + "\n"
        _append_chat_memory("assistant", response_text)
        yield "\n"
        return

    def _is_abab_cycle(fingerprints):
        if len(fingerprints) < 4:
            return False
        a, b, c, d = fingerprints[-4:]
        return a == c and b == d and a != b

    try:
        if max_rounds_override is not None:
            max_rounds = int(max_rounds_override)
            logger.info("使用自定义轮数: %d", max_rounds)
        else:
            max_rounds = int(AI_CONFIG.get("agent_max_rounds", 12))
        if max_rounds < 1:
            max_rounds = 1
        if max_rounds > 30:
            max_rounds = 30
        request_messages = _get_chat_messages_with_memory(user_message)
        aggregated_commands = []
        final_answer_text = ""
        finish_reason = ""
        no_progress_rounds = 0
        last_state_fingerprint = None
        recent_state_fingerprints = []
        cycle_rounds = 0
        last_execution_error = ""
        same_error_rounds = 0
        no_progress_stop_rounds = int(AI_CONFIG.get("agent_no_progress_stop_rounds", 4))
        if no_progress_stop_rounds < 3:
            no_progress_stop_rounds = 3
        if no_progress_stop_rounds > 10:
            no_progress_stop_rounds = 10
        yield STREAM_THINKING_MARKER
        yield "已进入自治执行模式：计划→执行→检查→按需继续。\n"

        for round_idx in range(1, max_rounds + 1):
            current_state = circuit_manager.get_state()
            compact_state = _build_compact_state(current_state)
            compact_state_json = json.dumps(compact_state, ensure_ascii=False, separators=(',', ':'))
            functions_data = circuit_manager._load_functions()
            available_functions = [f.get('name') for f in functions_data] if functions_data else []
            functions_str = f"可用自定义函数: {', '.join(available_functions)}" if available_functions else "当前无自定义函数"
            system_prompt = _build_autonomous_system_prompt(compact_state_json, functions_str)

            full_content = ""
            last_cmd_last_id = None
            executed_command_count = 0
            executed_success_count = 0
            command_errors = []
            command_results = []
            execution_error = ""
            in_commands = False
            outside_buf = ""
            commands_buf = ""
            commands_truncated = False
            MAX_CMDS_PER_ROUND = 30

            def _execute_one_command(cmd_data):
                nonlocal last_cmd_last_id, executed_command_count, executed_success_count, command_errors, command_results, commands_truncated
                if executed_command_count >= MAX_CMDS_PER_ROUND:
                    commands_truncated = True
                    return
                cmd = cmd_data.get("command")
                params = dict(cmd_data.get("params") or {})
                for k in ("id", "from_id", "to_id"):
                    if params.get(k) == "$last" and last_cmd_last_id:
                        params[k] = last_cmd_last_id
                cmd_data = {"command": cmd, "params": params}
                summary = _execute_commands_with_alias([cmd_data]) or {}
                executed_command_count += 1
                executed_success_count += int(summary.get("executed_success") or 0)
                command_errors.extend(list(summary.get("errors") or []))
                command_results.extend(list(summary.get("results") or []))
                if cmd == "add_element":
                    for r in (summary.get("results") or []):
                        if isinstance(r, dict) and r.get("command") == "add_element":
                            res = r.get("result")
                            if isinstance(res, dict) and res.get("id"):
                                last_cmd_last_id = res.get("id")
                                break
                if int(summary.get("executed_success") or 0) > 0 and cmd not in ("sample_outputs", "simulate"):
                    yield STREAM_STATE_CHANGED_MARKER

            def _feed_stream_text(text):
                nonlocal in_commands, outside_buf, commands_buf
                remaining = text or ""
                while remaining:
                    if not in_commands:
                        outside_buf += remaining
                        idx = outside_buf.lower().find("<commands>")
                        if idx == -1:
                            if len(outside_buf) > 200:
                                outside_buf = outside_buf[-200:]
                            return
                        after = outside_buf[idx + len("<commands>"):]
                        outside_buf = ""
                        in_commands = True
                        remaining = after
                        continue

                    commands_buf += remaining
                    remaining = ""

                    close_idx = commands_buf.lower().find("</commands>")
                    if close_idx != -1:
                        segment = commands_buf[:close_idx]
                        remainder = commands_buf[close_idx + len("</commands>"):]
                        commands_buf = ""
                        in_commands = False
                        for line in segment.splitlines():
                            line = line.strip()
                            if not line or line.startswith("```"):
                                continue
                            parsed = _parse_commands_payload(line)
                            for cmd_data in parsed:
                                for marker in _execute_one_command(cmd_data):
                                    yield marker
                        remaining = remainder
                        continue

                    if "\n" not in commands_buf:
                        return
                    lines = commands_buf.split("\n")
                    commands_buf = lines[-1]
                    for raw_line in lines[:-1]:
                        line = raw_line.strip()
                        if not line or line.startswith("```"):
                            continue
                        parsed = _parse_commands_payload(line)
                        for cmd_data in parsed:
                            for marker in _execute_one_command(cmd_data):
                                yield marker
                    return

            try:
                for chunk, fr in _call_llm_streaming(system_prompt, request_messages, thinking_mode=thinking_mode):
                    if fr:
                        finish_reason = fr
                    if chunk:
                        full_content += chunk
                        yield chunk
                        for marker in _feed_stream_text(chunk):
                            yield marker
            except Exception as e:
                execution_error = str(e)
                yield f"[第{round_idx}轮调用异常] {execution_error}\n"

            request_messages.append({"role": "assistant", "content": full_content})

            plan_text = _extract_tag_text(full_content, "plan")
            answer_text = _extract_answer_text(full_content)
            commands_text = _extract_commands_block(full_content)
            done_flag = _is_done_response(full_content)
            verify_obj = _extract_verify_payload(full_content)

            if not answer_text:
                answer_text = "已完成本轮处理。"
            final_answer_text = answer_text

            if commands_text:
                aggregated_commands.append(commands_text)

            after_state = circuit_manager.get_state()
            compact_after_state = _build_compact_state(after_state)
            state_fingerprint = json.dumps(compact_after_state, ensure_ascii=False, separators=(',', ':'))
            io_summary = _build_io_summary(after_state)
            if last_state_fingerprint is not None and state_fingerprint == last_state_fingerprint:
                no_progress_rounds += 1
            else:
                no_progress_rounds = 0
            last_state_fingerprint = state_fingerprint
            recent_state_fingerprints.append(state_fingerprint)
            if len(recent_state_fingerprints) > 6:
                recent_state_fingerprints.pop(0)
            if _is_abab_cycle(recent_state_fingerprints):
                cycle_rounds += 1
            else:
                cycle_rounds = 0

            element_count = len(compact_after_state.get('elements', []))
            wire_count = len(compact_after_state.get('wires', []))
            function_count = len(circuit_manager._load_functions())
            if command_errors:
                yield f"[第{round_idx}轮检查] elements={element_count}, wires={wire_count}, functions={function_count}, commands={executed_command_count}, ok={executed_success_count}, fail={len(command_errors)}\n"
            else:
                yield f"[第{round_idx}轮检查] elements={element_count}, wires={wire_count}, functions={function_count}, commands={executed_command_count}\n"

            if commands_truncated:
                yield f"[系统] 本轮命令数已达上限({MAX_CMDS_PER_ROUND})，剩余命令截断不执行，请在下轮继续。\n"
                request_messages.append({
                    "role": "user",
                    "content": f"系统：本轮命令数已达上限({MAX_CMDS_PER_ROUND}条)，你的后续命令已被截断。请在下轮补充剩余命令。"
                })
                done_flag = False

            if execution_error:
                if execution_error == last_execution_error:
                    same_error_rounds += 1
                else:
                    same_error_rounds = 1
                last_execution_error = execution_error
                if same_error_rounds >= 2:
                    final_answer_text = (
                        f"连续多轮执行命令失败（相同错误重复 {same_error_rounds} 次）：{execution_error}。"
                        "为避免无效重试，我已停止自治循环。你可以要求我改用更保守的命令或先清理/重建相关部分。"
                    )
                    break
                request_messages.append({
                    "role": "user",
                    "content": f"系统检查：第{round_idx}轮执行发生错误：{execution_error}。请修复并继续。"
                })
                continue
            last_execution_error = ""
            same_error_rounds = 0

            if command_errors:
                done_flag = False
                preview = command_errors[:5]
                lines = []
                for err in preview:
                    c = err.get("command")
                    m = err.get("error")
                    if c and m:
                        lines.append(f"- {c}: {m}")
                msg = "系统检查：本轮部分命令执行失败，请修复后继续。\n" + ("\n".join(lines) if lines else "")
                request_messages.append({"role": "user", "content": msg})

            sample_payloads = [r.get("result") for r in command_results if isinstance(r, dict) and r.get("command") == "sample_outputs"]
            if sample_payloads:
                latest = sample_payloads[-1]
                request_messages.append({"role": "user", "content": f"系统采样结果：{json.dumps(latest, ensure_ascii=False, separators=(',', ':'))}"})
            else:
                request_messages.append({"role": "user", "content": f"系统IO摘要：{json.dumps(io_summary, ensure_ascii=False, separators=(',', ':'))}"})

            verify_report = None
            if verify_obj is not None:
                verify_report = _run_verify_cases(verify_obj)
                if verify_report is None:
                    request_messages.append({"role": "user", "content": "系统验证失败：<verify> 内容无法解析或为空。请输出合法 JSON 并重试。"})
                    done_flag = False
                else:
                    report_text = json.dumps(verify_report, ensure_ascii=False, separators=(',', ':'))
                    request_messages.append({"role": "user", "content": f"系统验证报告：{report_text}"})
                    if verify_report.get("failed", 0) > 0:
                        done_flag = False

            if done_flag:
                break

            if cycle_rounds >= 2:
                final_answer_text = (
                    "检测到电路状态在少数几个状态之间循环变化（可能反复 TOGGLE 或反复增删无效）。"
                    "为避免无效调用，我已停止自治循环。你可以指定更明确的目标或允许我先重置关键输入再测试。"
                )
                break

            if no_progress_rounds >= no_progress_stop_rounds:
                final_answer_text = (
                    f"已连续 {no_progress_rounds} 轮状态无变化（疑似停滞）。"
                    "为避免无效调用，我已停止自治循环。你可以补充更具体的目标、允许我 CLEAR 重建、或指出需要保留的部分。"
                )
                break

            if no_progress_rounds >= 2:
                request_messages.append({
                    "role": "user",
                    "content": (
                        "系统约束：你已连续两轮没有产生任何有效命令且状态也未变化。"
                        "如果目标需要改动画布，你必须输出可执行命令并保持 done=false；"
                        "如果确实无需改动，请明确解释原因并输出 done=true。"
                    )
                })
                continue

            if executed_command_count == 0 and not done_flag:
                request_messages.append({
                    "role": "user",
                    "content": (
                        "系统提醒：你本轮没有输出可执行命令且 done=false。"
                        "如果确实无需改动，请把 done 设为 true 并解释原因；"
                        "否则请输出下一步可执行命令。"
                    )
                })

        yield STREAM_ANSWER_MARKER
        final_output = final_answer_text.strip() if final_answer_text else "已完成处理。"
        if aggregated_commands:
            merged_commands = "\n".join([c for c in aggregated_commands if c.strip()]).strip()
            final_output += f"\n<commands>\n{merged_commands}\n</commands>"
        else:
            final_output += "\n<commands>\n[]\n</commands>"
        yield final_output

        assistant_memory_text = _strip_commands_from_reply(final_output)
        _append_chat_memory("user", user_message)
        _append_chat_memory("assistant", assistant_memory_text)

        if finish_reason in {"length", "max_tokens"}:
            yield "\n[系统] 输出达到 max_tokens 上限，思考或回复可能被截断。可在 AI_CONFIG 中调大 max_tokens。"
                
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
        max_rounds = data.get('max_rounds', None)
        thinking_mode = data.get('thinking_mode', False)
        logger.info("/api/chat 接收到的 max_rounds=%s, thinking_mode=%s", max_rounds, thinking_mode)
        
        def generate():
            for chunk in call_llm_stream(message, max_rounds_override=max_rounds, thinking_mode=thinking_mode):
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
            try:
                with open(FUNCTIONS_DATA_FILE, 'r', encoding='utf-8') as f:
                    functions_data = json.load(f)
            except json.JSONDecodeError:
                functions_data = {'functions': []}
        
        # 添加新函数
        functions_data['functions'].append(new_function)
        
        _atomic_write_json(FUNCTIONS_DATA_FILE, functions_data)
        logger.info("函数已保存到: %s", FUNCTIONS_DATA_FILE)
        return jsonify({'status': 'success', 'message': 'Function saved successfully'})
    except Exception as e:
        logger.error("保存函数失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save-functions', methods=['POST', 'OPTIONS'])
def save_functions():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        _atomic_write_json(FUNCTIONS_DATA_FILE, data)
        logger.info("函数列表已保存到: %s", FUNCTIONS_DATA_FILE)
        return jsonify({'status': 'success', 'message': 'Functions saved successfully'})
    except Exception as e:
        logger.error("保存函数列表失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/load-functions', methods=['GET', 'OPTIONS'])
def load_functions():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        if os.path.exists(FUNCTIONS_DATA_FILE):
            try:
                with open(FUNCTIONS_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                logger.warning("函数数据文件损坏，使用空结构: %s", FUNCTIONS_DATA_FILE)
                data = {'functions': []}
            logger.info("函数数据已加载，包含 %d 个函数", len(data.get('functions', [])))
            return jsonify(data)
        else:
            return jsonify({'functions': []})
    except Exception as e:
        logger.error("加载函数数据失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    logger.info("电路设计应用启动中...")
    logger.info("电路数据文件路径: %s", CIRCUIT_DATA_FILE)
    logger.info("函数数据文件路径: %s", FUNCTIONS_DATA_FILE)
    logger.info("打开软件: http://localhost:5000")
    # 禁用Flask的开发服务器banner
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    app.run(debug=False, host='0.0.0.0', port=5000)
