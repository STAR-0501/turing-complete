from flask import Flask, request, jsonify, render_template, Response
import json
import os
import logging
import sys
from ai_commands import CircuitManager
import re
import requests
import time
import threading

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
    elif cmd == 'move_element':
        return circuit_manager.move_element(params['id'], params['x'], params['y'])
    elif cmd == 'get_state':
        return circuit_manager.get_state()
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
        for _ in range(retries):
            if not pending_wires:
                break
            unresolved_wires = []
            executed_count = 0
            for wire_params in pending_wires:
                try:
                    _try_execute_wire(wire_params)
                    executed_count += 1
                except:
                    unresolved_wires.append(wire_params)
            pending_wires = unresolved_wires
            if executed_count == 0:
                break

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
            except:
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

        if cmd in ('clear_circuit', 'define_function', 'remove_element', 'remove_wire'):
            _flush_pending_wires()

        try:
            execute_circuit_command(cmd, params)
        except:
            continue

    _flush_pending_wires()
    try:
        circuit_manager.simulate()
    except:
        pass

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

逻辑参考 (标准门实现):
- NAND(A, B): NOT(AND(A, B))
- NOR(A, B): NOT(OR(A, B))
- XOR(A, B): OR(AND(A, NOT(B)), AND(NOT(A), B))
- HalfAdder(A, B): SUM = XOR(A, B), CARRY = AND(A, B)

规则:
- 基础门只允许 AND、OR、NOT、INPUT、OUTPUT。严禁直接使用 XOR 等。
- 必须使用函数思维：复杂逻辑先搭建 -> DEFINE_FUNC -> CLEAR -> ADD <函数名> 复用。
- 布局美观：使用 MOVE 调整位置，避免元件重叠。
- 验证驱动：如果你不确定电路是否正确，可以使用 TOGGLE 切换输入并观察 elements 的 state 变化。
- 强烈建议：给关键元件设置 alias（ADD 第 5 个参数）。alias 会持久化，后续所有 <id_or_alias> 都可以直接使用 alias。
- done 的标准：只有当你已经用 state（必要时用 TOGGLE 做测试）验证目标达成，且不需要再执行任何命令时，才输出 done=true。
- 如果用户目标需要改动画布，但你在本轮没有输出任何可执行命令，则 done 必须为 false，并给出下一步命令或说明阻碍点。

当前函数信息:
""" + functions_str + """

当前电路状态 (含实时逻辑电平 state):
""" + compact_state_json + """

你必须严格输出以下结构:
<plan>
1. 分析当前状态 2. 制定本轮操作 3. 预期逻辑行为
</plan>
<answer>
给用户的简短说明
</answer>
<commands>
命令列表
</commands>
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

def call_llm_stream(user_message):
    if AI_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        yield "请先在 app.py 中配置您的 AI_CONFIG['api_key']。"
        return

    def _is_abab_cycle(fingerprints):
        if len(fingerprints) < 4:
            return False
        a, b, c, d = fingerprints[-4:]
        return a == c and b == d and a != b

    try:
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

            full_content, finish_reason = _call_llm_once(system_prompt, request_messages)
            request_messages.append({"role": "assistant", "content": full_content})

            plan_text = _extract_tag_text(full_content, "plan")
            answer_text = _extract_answer_text(full_content)
            commands_text = _extract_commands_block(full_content)
            done_flag = _is_done_response(full_content)

            if not answer_text:
                answer_text = "已完成本轮处理。"
            final_answer_text = answer_text

            if plan_text:
                yield f"[第{round_idx}轮计划]\n{plan_text}\n"
            else:
                yield f"[第{round_idx}轮计划]\n先执行必要操作，再进行结果检查。\n"

            executed_command_count = 0
            execution_error = ""
            if commands_text:
                try:
                    parsed_commands = _parse_commands_payload(commands_text)
                    executed_command_count = len(parsed_commands)
                    _execute_commands_with_alias(parsed_commands)
                    aggregated_commands.append(commands_text)
                    if executed_command_count > 0:
                        yield STREAM_STATE_CHANGED_MARKER
                except Exception as e:
                    execution_error = str(e)
                    yield f"[第{round_idx}轮执行异常] {execution_error}\n"

            after_state = circuit_manager.get_state()
            compact_after_state = _build_compact_state(after_state)
            state_fingerprint = json.dumps(compact_after_state, ensure_ascii=False, separators=(',', ':'))
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
            yield f"[第{round_idx}轮检查] elements={element_count}, wires={wire_count}, functions={function_count}, commands={executed_command_count}\n"

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
