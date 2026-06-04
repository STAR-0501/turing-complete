from flask import Flask, request, jsonify, render_template, Response
import glob
import json
import os
import logging
import sys
from ai_commands import CircuitManager
from subagent_manager import SubagentManager
import re
import requests
import tempfile
import time
import threading
import copy
import uuid
from turing_compactor import OverflowDetector, ContextCompactor
from permissions import PermissionChecker, Permission
from retry import retry_call

# AI 配置 (请在此填入您的 API Key)
# 可选的 agent 参数:
#   agent_max_rounds: 自治循环最大轮数 (默认 100，无硬上限，最小 1)
#   agent_max_cmds_per_round: 每轮最多执行命令数 (默认 200，无硬上限，最小 10)
#   agent_no_progress_stop_rounds: 连续无变化多少轮后停止 (默认 30，无硬上限，最小 3)
#   max_tokens: 每次 LLM 调用的输出长度上限 (默认 4000)
#   connect_timeout: 连接超时秒数 (默认 10)
#   read_timeout: 读取超时秒数 (默认 180)
# AI 配置管理 - 从 ai_config.json 文件加载
CONFIG_FILE = "ai_config.json"
_AI_CONFIG_DEFAULTS = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "max_tokens": 4000,
    "connect_timeout": 10,
    "read_timeout": 180,
    "protocol": "",
    "anthropic_version": "2023-06-01",
    "agent_max_rounds": 100,
    "agent_max_cmds_per_round": 200,
    "agent_no_progress_stop_rounds": 30
}
_ai_config_cache = None


def load_ai_config():
    global _ai_config_cache
    config = dict(_AI_CONFIG_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    _ai_config_cache = config
    return config


def get_ai_config():
    global _ai_config_cache
    if _ai_config_cache is None:
        return load_ai_config()
    return _ai_config_cache


def save_ai_config(data):
    global _ai_config_cache
    config = get_ai_config()
    config.update(data)
    _atomic_write_json(CONFIG_FILE, config)
    _ai_config_cache = config
    return config


def is_ai_configured():
    cfg = get_ai_config()
    key = cfg.get("api_key", "")
    return bool(key) and key != "YOUR_API_KEY_HERE"


def _build_api_url(endpoint, base_url=None):
    """构建 API URL，防止用户提供的 base_url 已包含路径时重复拼接。
    
    Args:
        endpoint: API 路径，如 '/chat/completions'
        base_url: 可选自定义 base_url，默认从保存的 config 中读取
    """
    if base_url is None:
        base_url = get_ai_config()['base_url']
    base = str(base_url).rstrip('/')
    if base.endswith(endpoint):
        return base
    return f"{base}{endpoint}"


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
ROUND_MARKER = "__TC_ROUND__"
chat_memory = []
chat_memory_lock = threading.Lock()

# 获取当前文件所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 存储电路数据的文件
CIRCUIT_DATA_FILE = os.path.join(BASE_DIR, 'circuit_data.json')
# 存储模块数据的文件
MODULES_DATA_FILE = os.path.join(BASE_DIR, 'modules_data.json')
# AI 模式持久化文件
PLAN_FILE = os.path.join(BASE_DIR, 'plan.md')
SUMMARY_FILE = os.path.join(BASE_DIR, 'summary.md')
SKILLS_FILE = os.path.join(BASE_DIR, 'skills.md')
# 日志文件夹
LOG_DIR = os.path.join(BASE_DIR, 'log')

# 初始化电路管理器
circuit_manager = CircuitManager(CIRCUIT_DATA_FILE, MODULES_DATA_FILE)
# 权限检查器（默认 WRITE：允许读写仿真和添加，禁止删除/清除）
perm_checker = PermissionChecker(level=Permission.WRITE)
# 子代理管理器（并发执行独立电路任务）
subagent_manager = SubagentManager()

# 初始化：如果文件不存在，创建一个空的电路数据文件


def init_circuit_file():
    if not os.path.exists(CIRCUIT_DATA_FILE):
        try:
            with open(CIRCUIT_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'elements': [], 'wires': []},
                          f, indent=2, ensure_ascii=False)
            logger.info("已创建空的电路数据文件: %s", CIRCUIT_DATA_FILE)
        except Exception as e:
            logger.error("创建电路数据文件失败: %s", e)

# 初始化：如果文件不存在，创建一个空的模块数据文件


def init_modules_file():
    if not os.path.exists(MODULES_DATA_FILE):
        try:
            with open(MODULES_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'modules': []}, f, indent=2, ensure_ascii=False)
            logger.info("已创建空的模块数据文件: %s", MODULES_DATA_FILE)
        except Exception as e:
            logger.error("创建模块数据文件失败: %s", e)

# 初始化 AI 计划文件


def init_plan_file():
    if not os.path.exists(PLAN_FILE):
        try:
            with open(PLAN_FILE, 'w', encoding='utf-8') as f:
                f.write(
                    "# AI Circuit Building Plan\n\n## Objective\n\n\n## Tasks\n\n")
            logger.info("已创建 AI 计划文件: %s", PLAN_FILE)
        except Exception as e:
            logger.error("创建计划文件失败: %s", e)


def init_summary_file():
    if not os.path.exists(SUMMARY_FILE):
        try:
            with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
                f.write(
                    "# AI Session Summary\n\n## State\n\n\n## Progress\n\n\n## Issues\n\n")
            logger.info("已创建 AI 摘要文件: %s", SUMMARY_FILE)
        except Exception as e:
            logger.error("创建摘要文件失败: %s", e)


def init_skills_file():
    if not os.path.exists(SKILLS_FILE):
        try:
            with open(SKILLS_FILE, 'w', encoding='utf-8') as f:
                f.write(
                    "# Agent Skills (Self-Evolving Knowledge Base)\n\n_Last updated: 2026-05-14_\n_Total skills: 0_\n\n")
            logger.info("已创建自学技能文件: %s", SKILLS_FILE)
        except Exception as e:
            logger.error("创建技能文件失败: %s", e)


def _atomic_write_md(path, content):
    """原子写入 Markdown 文件（plan.md / summary.md）。"""
    dir_name = os.path.dirname(path) or os.getcwd()
    for stale in glob.glob(f"{path}.tmp.*"):
        try:
            os.remove(stale)
        except OSError:
            pass
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=dir_name, prefix=f".{os.path.basename(path)}.tmp.",
        delete=False
    ) as f:
        f.write(content)
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


def _load_md_file(path):
    """加载 Markdown 文件，若不存在返回空字符串。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""

# ========== 对话日志系统 ==========


def _init_log_dir():
    """确保日志目录存在。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.error("创建日志目录失败: %s", e)


def _log_conversation(entry_type, content, session_id=None, round_num=None):
    """将 JSONL 日志条目追加到按对话命名的日志文件中。

    entry_type: 'user', 'assistant', 'system', 'llm_request', 'llm_response', 'command', 'observe', 'plan', 'summary' 之一
    session_id: 对话唯一标识。不传时按日期分文件（向后兼容）。
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        if session_id:
            today = time.strftime('%Y%m%d')
            log_file = os.path.join(LOG_DIR, f'conversation_{today}_{session_id}.jsonl')
        else:
            today = time.strftime('%Y%m%d')
            log_file = os.path.join(LOG_DIR, f'conversation_{today}.jsonl')
        entry = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": entry_type,
            "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        }
        if session_id:
            entry["session"] = session_id
        if round_num is not None:
            entry["round"] = round_num
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error("写入日志失败: %s", e)


# 启动时初始化
init_circuit_file()
init_modules_file()
init_plan_file()
init_summary_file()
init_skills_file()


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
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
def api_get_config():
    cfg = get_ai_config()
    return jsonify({
        'configured': is_ai_configured(),
        'base_url': cfg.get('base_url', ''),
        'model': cfg.get('model', ''),
        'max_tokens': cfg.get('max_tokens', 4000),
        'connect_timeout': cfg.get('connect_timeout', 10),
        'read_timeout': cfg.get('read_timeout', 180)
    })


@app.route('/api/config', methods=['POST'])
def api_set_config():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data'}), 400
        save_ai_config(data)
        return jsonify({'status': 'ok', 'configured': is_ai_configured()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/test-apikey', methods=['POST'])
def api_test_apikey():
    """测试 API Key 是否有效。
    接受与 /api/config 相同的字段，做一次最小 API 调用验证。
    """
    try:
        data = request.get_json() or {}
        api_key = data.get('api_key', '').strip()
        base_url = data.get('base_url', '').strip() or 'https://api.deepseek.com'
        model = data.get('model', '').strip() or 'deepseek-v4-flash'

        if not api_key:
            return jsonify({'status': 'error', 'message': '请输入 API Key'}), 400

        # 判断协议并使用 _build_api_url 防止路径重复
        base_lower = base_url.lower()
        if '/anthropic' in base_lower:
            test_url = _build_api_url('/messages', base_url=base_url)
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'max_tokens': 10,
                'messages': [{'role': 'user', 'content': 'hi'}]
            }
        else:
            test_url = _build_api_url('/chat/completions', base_url=base_url)
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 5
            }

        resp = requests.post(test_url, headers=headers, json=payload, timeout=15)

        if resp.status_code == 200:
            return jsonify({'status': 'ok', 'message': '✓ API Key 有效，连接正常'})
        elif resp.status_code == 401:
            return jsonify({'status': 'error', 'message': 'API Key 无效或被拒绝（401）'})
        elif resp.status_code == 403:
            return jsonify({'status': 'error', 'message': 'API Key 权限不足（403）'})
        elif resp.status_code == 429:
            return jsonify({'status': 'error', 'message': '请求过于频繁，请稍后重试（429）'})
        else:
            detail = resp.text[:200]
            return jsonify({'status': 'error', 'message': f'API 返回错误 ({resp.status_code}): {detail}'})

    except requests.exceptions.ConnectTimeout:
        return jsonify({'status': 'error', 'message': f'连接超时（{data.get("base_url","")}），请检查地址或网络'})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': f'无法连接到 {data.get("base_url","")}，请检查地址或网络'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'测试失败: {str(e)}'}), 500


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
        if not is_ai_configured():
            return jsonify({'status': 'error', 'message': '请先在 Agent 侧边栏配置 API 参数'}), 400

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
                "moduleName": el.get("name") if el.get("type") == "FUNCTION" else None
            }
            elements_info.append(el_info)

        wires_info = []
        for w in wires:
            start_el = next((e for e in elements if e.get(
                "id") == w.get("start", {}).get("elementId")), None)
            end_el = next((e for e in elements if e.get("id") ==
                          w.get("end", {}).get("elementId")), None)
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
            _build_api_url('/chat/completions'),
            headers={
                "Authorization": f"Bearer {get_ai_config()['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": get_ai_config().get("model", "default"),
                "messages": messages,
                "temperature": 0.3
            },
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'status': 'error', 'message': f'AI API 错误: {response.text}'}), 500

        result = response.json()
        content = result.get("choices", [{}])[0].get(
            "message", {}).get("content", "{}")

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
        if not is_ai_configured():
            return jsonify({'status': 'error', 'message': '请先在 Agent 侧边栏配置 API 参数'}), 400

        current_state = circuit_manager.get_state()
        elements = current_state.get('elements', [])

        if not elements:
            return jsonify({'status': 'success', 'positions': {}})

        user_message = """请整理这个电路的布局。

要求：
1. 尽可能保持正方形，不是一直向下或者向右；
2. 尽可能体现这个电路的功能，让人一眼能看懂电路，符合人的阅读习惯；
3. 如果是二进制数字，应当保证把高位到低位按照从左到右的顺序排，比如一个三位数，用了三个输入（或者输出）模块，那么最高位应当在最左边，最低为应当在最右边，不论是输入还是输出，都必须按这个要求排列，不能从上到下排。

请根据当前电路状态分析布局，输出 MOVE 命令来调整元件位置。"""

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
        if not is_ai_configured():
            return jsonify({'status': 'error', 'message': '请先在 Agent 侧边栏配置 API 参数'}), 400

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
    执行命令并返回结果的辅助模块
    """
    # 权限检查
    allowed, err = perm_checker.check(cmd)
    if not allowed:
        raise PermissionError(err)
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
    elif cmd == 'define_module':
        return circuit_manager.define_module(params['name'])
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

        # JSON 工具调用格式: {"tool": "add_element", "params": {...}}
        if line.startswith('{'):
            try:
                j = json.loads(line)
                tool = j.get('tool')
                params = j.get('params', {})
                if tool and isinstance(params, dict):
                    commands.append({'command': tool, 'params': params})
                    continue
            except json.JSONDecodeError:
                pass

        parts = [_clean_token(p) for p in line.split() if _clean_token(p)]
        if not parts:
            continue

        cmd = _clean_token(parts[0]).upper()

        try:
            if cmd == 'ADD':
                if len(parts) >= 4:
                    element_type = _clean_token(parts[1]).upper()
                    # 此处移除严格类型检查，以允许自定义模块名
                    # 或者检查是否在允许的基础类型中，或交由 CircuitManager 处理
                    params = {
                        'type': element_type if element_type in {'AND', 'OR', 'NOT', 'INPUT', 'OUTPUT'} else _clean_token(parts[1]),
                        'x': float(_clean_token(parts[2])),
                        'y': float(_clean_token(parts[3]))
                    }
                    if len(parts) >= 5:
                        params['alias'] = _clean_token(parts[4])
                    commands.append(
                        {'command': 'add_element', 'params': params})
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
                    commands.append({'command': 'remove_element', 'params': {
                                    'id': _clean_token(parts[1])}})
            elif cmd == 'DELW':
                if len(parts) >= 2:
                    commands.append({'command': 'remove_wire', 'params': {
                                    'id': _clean_token(parts[1])}})
            elif cmd == 'CLEAR':
                commands.append({'command': 'clear_circuit', 'params': {}})
            elif cmd == 'DEFINE_FUNC':
                if len(parts) >= 2:
                    commands.append({'command': 'define_module', 'params': {
                                    'name': _clean_token(parts[1])}})
            elif cmd == 'TOGGLE':
                if len(parts) >= 2:
                    commands.append({'command': 'toggle_input', 'params': {
                                    'id': _clean_token(parts[1])}})
            elif cmd == 'SET':
                if len(parts) >= 3:
                    v = _parse_bool_token(parts[2])
                    if v is not None:
                        commands.append({'command': 'set_input', 'params': {
                                        'id': _clean_token(parts[1]), 'value': v}})
            elif cmd in ('SIM', 'SIMULATE'):
                commands.append({'command': 'simulate', 'params': {}})
            elif cmd == 'SAMPLE':
                ids = [_clean_token(p)
                       for p in parts[1:]] if len(parts) > 1 else []
                params = {'ids': ids} if ids else {}
                commands.append(
                    {'command': 'sample_outputs', 'params': params})
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
        from_ref = params.pop('from_ref', None) or params.pop(
            'from_alias', None)
        to_ref = params.pop('to_ref', None) or params.pop('to_alias', None)

        if from_ref and not params.get('from_id'):
            params['from_id'] = _resolve_element_ref(from_ref, alias_map)
        else:
            params['from_id'] = _resolve_element_ref(
                params.get('from_id'), alias_map)

        if to_ref and not params.get('to_id'):
            params['to_id'] = _resolve_element_ref(to_ref, alias_map)
        else:
            params['to_id'] = _resolve_element_ref(
                params.get('to_id'), alias_map)

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
                msg = last_failures[idx] if idx < len(
                    last_failures) else "无法连接导线"
                errors.append(
                    {"command": "add_wire", "error": msg, "params": wire_params})
            pending_wires = []

    for cmd_data in commands:
        cmd = cmd_data.get('command')
        params = dict(cmd_data.get('params', {}) or {})

        if cmd == 'add_element':
            specified_alias = params.pop('alias', None) or params.pop(
                'ref', None) or params.pop('name', None)
            alias = specified_alias
            try:
                if specified_alias:
                    params['alias'] = specified_alias
                result = execute_circuit_command(cmd, params)
                executed_success += 1
                results.append({"command": "add_element", "result": {
                               "id": result.get("id")} if isinstance(result, dict) else "ok"})
            except Exception as e:
                errors.append({"command": "add_element",
                              "error": str(e), "params": params})
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
            params['ids'] = [_resolve_element_ref(
                v, alias_map) for v in params.get('ids') if v is not None]

        if cmd in ('clear_circuit', 'define_module', 'remove_element', 'remove_wire'):
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
            'name': e.get('name') if e.get('type') == 'FUNCTION' else None,
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


def _compute_state_diff(old_state, new_state):
    old_el = {e["id"]: e for e in (old_state or {}).get("elements", [])}
    new_el = {e["id"]: e for e in (new_state or {}).get("elements", [])}

    added = []
    for eid, e in new_el.items():
        if eid not in old_el:
            added.append({"id": e["id"], "type": e["type"], "alias": e.get(
                "alias"), "pos": [e.get("x"), e.get("y")]})

    removed = [{"id": e["id"], "type": e["type"]}
               for eid, e in old_el.items() if eid not in new_el]

    changed = []
    for eid, e in new_el.items():
        if eid in old_el:
            o = old_el[eid]
            if e.get("x") != o.get("x") or e.get("y") != o.get("y"):
                changed.append({"id": eid, "change": "position", "from": [
                               o.get("x"), o.get("y")], "to": [e.get("x"), e.get("y")]})
            if e.get("state") != o.get("state"):
                changed.append({"id": eid, "change": "state",
                               "from": o.get("state"), "to": e.get("state")})
            if e.get("comment") != o.get("comment"):
                changed.append({"id": eid, "change": "comment", "from": o.get(
                    "comment"), "to": e.get("comment")})

    old_wires = {}
    for w in (old_state or {}).get("wires", []):
        if "start" in w and "end" in w:
            key = (w["start"].get("elementId"), w["end"].get("elementId"))
            old_wires[key] = w.get("id")

    new_wires = {}
    for w in (new_state or {}).get("wires", []):
        if "start" in w and "end" in w:
            key = (w["start"].get("elementId"), w["end"].get("elementId"))
            new_wires[key] = w.get("id")

    wires_added = [{"id": wid, "from": conn[0], "to": conn[1]}
                   for conn, wid in new_wires.items() if conn not in old_wires]
    wires_removed = [{"id": wid, "from": conn[0], "to": conn[1]}
                     for conn, wid in old_wires.items() if conn not in new_wires]

    return {
        "elements_added": added,
        "elements_removed": removed,
        "elements_changed": changed,
        "wires_added": wires_added,
        "wires_removed": wires_removed,
        "io_summary": _build_io_summary(new_state)
    }


def _build_io_summary(state):
    elements = (state or {}).get("elements") or []
    inputs = []
    outputs = []
    functions = []
    for e in elements:
        t = e.get("type")
        if t == "INPUT":
            inputs.append({"id": e.get("id"), "alias": e.get("alias") or e.get(
                "name"), "state": bool(e.get("state", False))})
        elif t == "OUTPUT":
            outputs.append({"id": e.get("id"), "alias": e.get("alias") or e.get(
                "name"), "state": bool(e.get("state", False))})
        elif t == "FUNCTION":
            functions.append({"id": e.get("id"), "alias": e.get(
                "alias"), "name": e.get("name"), "state": bool(e.get("state", False))})
    return {"inputs": inputs, "outputs": outputs, "functions": functions}


def _strip_commands_from_reply(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r'<commands>[\s\S]*?(</commands>|$)',
                  '', text, flags=re.DOTALL)
    text = re.sub(
        r'<(think|plan|build|observe|sum)>[\s\S]*?(</\1>|$)', '', text, flags=re.DOTALL)
    text = text.replace(ROUND_MARKER, '').replace('---\n', '')
    return text.strip()


def _normalize_memory_text(text):
    if not isinstance(text, str):
        return ""
    return text.strip()[:CHAT_MESSAGE_MAX_CHARS]


def _get_chat_messages_with_memory(user_message):
    with chat_memory_lock:
        messages = list(chat_memory)
    messages.append(
        {"role": "user", "content": _normalize_memory_text(user_message)})
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
    protocol = str(get_ai_config().get("protocol", "")).strip().lower()
    if protocol:
        return protocol
    base_url = str(get_ai_config().get("base_url", "")).lower()
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


def _extract_verify_payload_from_text(text):
    """将 observe/verify 内容（<observe>标签内的文本）解析为 JSON 测试用例。"""
    if not text or not text.strip():
        return None
    # 尝试在文本中查找 JSON（可能包含周围文本）
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            return None
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
        single = {"inputs": verify_obj.get(
            "inputs") or [], "expect": verify_obj.get("expect") or []}
        cases = [single]
    if not isinstance(cases, list) or not cases:
        return None

    max_cases = 16
    cases = cases[:max_cases]

    snapshot = copy.deepcopy(circuit_manager.get_state())
    try:
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
                    case_result["details"].append(
                        {"id": ref, "want": want, "got": got, "ok": ok})
            except Exception as e:
                case_result["pass"] = False
                case_result["details"].append({"error": str(e)})

            if case_result["pass"]:
                report["passed"] += 1
            else:
                report["failed"] += 1
            report["cases"].append(case_result)
    finally:
        circuit_manager._save_data(snapshot)

    return report


def _extract_commands_block(text):
    if not isinstance(text, str):
        return ""
    matches = re.findall(
        r'<commands>([\s\S]*?)</commands>', text, re.IGNORECASE)
    if matches:
        merged = "\n".join([m.strip()
                           for m in matches if m and m.strip()]).strip()
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
    stripped = re.sub(r'<plan>[\s\S]*?</plan>', '',
                      text, flags=re.IGNORECASE).strip()
    stripped = re.sub(r'<done>[\s\S]*?</done>', '',
                      stripped, flags=re.IGNORECASE).strip()
    stripped = _strip_commands_from_reply(stripped)
    return stripped


def _merge_skills(new_skills_text, existing_skills_text):
    """将新技能合并到现有 skills.md 内容中，按标题去重。

    返回更新后的 skills.md 内容，若无新技能返回空字符串。
    若合并失败（无变化）返回 None。
    """
    if not new_skills_text or not new_skills_text.strip():
        return None

    # 从新内容中提取技能标题（### Skill-*）
    if not new_headers:
        # 新文本中未找到有效技能
        return None

    # 清理新技能文本 - 移除 <skills> 包装结构
    # 可能包含分类标题和技能条目
    new_skills_clean = new_skills_text.strip()

    if not existing_skills_text or not existing_skills_text.strip():
        # 无现有技能 - 直接返回带标题的新技能
        today = time.strftime('%Y-%m-%d')
        new_count = len(new_headers)
        return f"# Agent Skills (Self-Evolving Knowledge Base)\n\n_Last updated: {today}_\n_Total skills: {new_count}_\n\n{new_skills_clean}\n"

    # 检查哪些标题已存在于现有文本中
    existing_headers = set(re.findall(
        r'^###\s+(Skill-[\w-]+)', existing_skills_text, re.MULTILINE))
    truly_new_headers = new_headers - existing_headers

    if not truly_new_headers:
        # 所有新技能已存在于现有技能中
        return None

    # 查找需要追加的新技能（按标题提取完整块）
    appended_blocks = []
    for header in truly_new_headers:
        # 在 new_skills_clean 中查找块（从标题到下一个标题或末尾）
        pattern = rf'(^###\s+{re.escape(header)}.*?)(?=\n###\s+Skill-|\Z)'
        match = re.search(pattern, new_skills_clean, re.DOTALL | re.MULTILINE)
        if match:
            block = match.group(1).strip()
            appended_blocks.append(block)

    if not appended_blocks:
        return None

    # 在页脚前追加新块（最后一行或"To add a new skill"部分之前）
    footer_marker = "\n---\n*To add a new skill"
    footer_idx = existing_skills_text.find(footer_marker)

    new_content = "\n\n".join(appended_blocks)

    if footer_idx >= 0:
        merged = existing_skills_text[:footer_idx] + "\n\n" + \
            new_content + "\n\n" + existing_skills_text[footer_idx:]
    else:
        merged = existing_skills_text.rstrip() + "\n\n" + new_content + "\n"

    # 更新总计数
    all_headers = existing_headers | truly_new_headers
    today = time.strftime('%Y-%m-%d')
    merged = re.sub(
        r'_Last updated:.*',
        f'_Last updated: {today}_',
        merged
    )
    merged = re.sub(
        r'_Total skills:\s*\d+',
        f'_Total skills: {len(all_headers)}',
        merged
    )

    return merged


TOOL_SCHEMAS = {
    "add_element": {
        "description": "添加元件到电路",
        "params": {"type": "enum(AND|OR|NOT|INPUT|OUTPUT|FUNCTION)", "x": "number", "y": "number", "alias": "string(可选)"},
        "text": "ADD <type> <x> <y> [alias]",
        "json_example": '{"tool": "add_element", "params": {"type": "AND", "x": 240, "y": 60, "alias": "g1"}}'
    },
    "add_wire": {
        "description": "连接两个元件的端口",
        "params": {"from_ref": "string", "from_port_idx": "int", "to_ref": "string", "to_port_idx": "int"},
        "text": "WIRE <from> <from_port> <to> <to_port>",
        "json_example": '{"tool": "add_wire", "params": {"from_ref": "g1", "from_port_idx": 0, "to_ref": "g2", "to_port_idx": 1}}'
    },
    "move_element": {
        "description": "移动元件位置",
        "params": {"id": "string", "x": "number", "y": "number"},
        "text": "MOVE <id> <x> <y>",
        "json_example": '{"tool": "move_element", "params": {"id": "abc123", "x": 300, "y": 100}}'
    },
    "remove_element": {
        "description": "删除元件及关联导线",
        "params": {"id": "string"},
        "text": "DEL <id>",
        "json_example": '{"tool": "remove_element", "params": {"id": "abc123"}}'
    },
    "remove_wire": {
        "description": "删除单根导线",
        "params": {"id": "string"},
        "text": "DELW <wire_id>",
        "json_example": '{"tool": "remove_wire", "params": {"id": "wire123"}}'
    },
    "clear_circuit": {
        "description": "清空画布所有元件和导线",
        "params": {},
        "text": "CLEAR",
        "json_example": '{"tool": "clear_circuit", "params": {}}'
    },
    "toggle_input": {
        "description": "切换 INPUT 元件的电平",
        "params": {"id": "string"},
        "text": "TOGGLE <id>",
        "json_example": '{"tool": "toggle_input", "params": {"id": "input1"}}'
    },
    "set_input": {
        "description": "将 INPUT 设置为指定电平",
        "params": {"id": "string", "value": "bool"},
        "text": "SET <id> <0|1>",
        "json_example": '{"tool": "set_input", "params": {"id": "A", "value": 1}}'
    },
    "simulate": {
        "description": "显式触发仿真传播",
        "params": {},
        "text": "SIM",
        "json_example": '{"tool": "simulate", "params": {}}'
    },
    "sample_outputs": {
        "description": "采样 OUTPUT 状态",
        "params": {"ids": "string[](可选,默认全部)"},
        "text": "SAMPLE [id ...]",
        "json_example": '{"tool": "sample_outputs", "params": {"ids": ["SUM", "CARRY"]}}'
    },
    "define_module": {
        "description": "将当前电路封装为自定义模块",
        "params": {"name": "string"},
        "text": "DEFINE_FUNC <name>",
        "json_example": '{"tool": "define_module", "params": {"name": "HalfAdder"}}'
    },
    "set_element_comment": {
        "description": "设置元件注释",
        "params": {"id": "string", "comment": "string"},
        "text": "COMMENT <id> <text>",
        "json_example": '{"tool": "set_element_comment", "params": {"id": "and1", "comment": "A与B相与"}}'
    }
}


def _format_feedback_text(feedback):
    if not feedback:
        return ""
    lines = []
    exe = feedback.get("execution", {})
    if exe:
        errors = exe.get("errors") or []
        lines.append("--- 本轮操作反馈 ---")
        lines.append(
            f"执行: {exe.get('success_count', 0)}/{exe.get('command_count', 0)} 条命令成功")
        if errors:
            lines.append(f"错误 ({len(errors)}):")
            for err in errors[:5]:
                c = err.get("command", "?")
                m = err.get("error", "?")
                lines.append(f"  - {c}: {m}")

    diff = feedback.get("state_diff")
    if diff:
        added = diff.get("elements_added") or []
        removed = diff.get("elements_removed") or []
        changed = diff.get("elements_changed") or []
        wires_added = diff.get("wires_added") or []
        wires_removed = diff.get("wires_removed") or []

        if added:
            lines.append(f"新增元件 ({len(added)}):")
            for el in added:
                alias = f" ({el.get('alias')})" if el.get("alias") else ""
                lines.append(
                    f"  + {el.get('type')} {el.get('id')}{alias} @ {el.get('pos')}")
        if removed:
            lines.append(f"移除元件 ({len(removed)}):")
            for el in removed:
                lines.append(f"  - {el.get('type')} {el.get('id')}")
        if changed:
            for c in changed:
                ct = c.get("change")
                if ct == "position":
                    lines.append(
                        f"  ~ {c.get('id')} 位置: {c.get('from')} -> {c.get('to')}")
                elif ct == "state":
                    lines.append(
                        f"  ~ {c.get('id')} 电平: {c.get('from')} -> {c.get('to')}")
                elif ct == "comment":
                    lines.append(f"  ~ {c.get('id')} 注释已更新")
        if wires_added:
            lines.append(f"新增连线 ({len(wires_added)}):")
            for w in wires_added:
                lines.append(f"  + {w.get('from')} -> {w.get('to')}")
        if wires_removed:
            lines.append(f"移除连线 ({len(wires_removed)}):")
            for w in wires_removed:
                lines.append(f"  - {w.get('from')} -> {w.get('to')}")

        io = diff.get("io_summary") or {}
        inputs = io.get("inputs") or []
        outputs = io.get("outputs") or []
        functions = io.get("functions") or []
        io_parts = []
        if inputs:
            in_strs = []
            for i in inputs:
                label = i.get("alias") or i.get("id")
                val = 1 if i.get("state") else 0
                in_strs.append(f"{label}={val}")
            io_parts.append("输入: " + ", ".join(in_strs))
        if outputs:
            out_strs = []
            for o in outputs:
                label = o.get("alias") or o.get("id")
                val = 1 if o.get("state") else 0
                out_strs.append(f"{label}={val}")
            io_parts.append("输出: " + ", ".join(out_strs))
        if functions:
            fn_strs = [f.get('name') or f.get('id') for f in functions]
            io_parts.append("模块: " + ", ".join(fn_strs))
        if io_parts:
            lines.append("当前 IO: " + " | ".join(io_parts))

    verify = feedback.get("verify_results")
    if verify:
        lines.append("--- 测试验证结果 ---")
        for v in (verify.get("cases") or []):
            icon = "✅" if v.get("pass") else "❌"
            lines.append(
                f"{icon} 测试 {v.get('index')}: {'通过' if v.get('pass') else '失败'}")
            for d in v.get("details") or []:
                if "error" in d:
                    lines.append(f"  ⚠️ {d['error']}")
                else:
                    status = "✅" if d.get("ok") else "❌"
                    lines.append(
                        f"  {status} {d['id']}: 期望={d.get('want')}, 实际={d.get('got')}")

    return "\n".join(lines)


def _build_autonomous_system_prompt(compact_state_json, modules_str, feedback=None,
                                    plan_content="", summary_content="", skills_content=""):
    base = """你是一个电路模拟器自治执行助手。你以 5 阶段循环工作：Think→Plan→Build→Observe→Sum。
每轮都必须依次输出这 5 个阶段的内容，系统会分别处理每个阶段。

可用工具（支持两种格式：传统文本 或 JSON）：

"""

    for tool_name, schema in TOOL_SCHEMAS.items():
        params_str = ", ".join(
            f"{k}({v})" for k, v in schema["params"].items())
        base += f"{schema['text']}\n"
        base += f"  JSON: {schema['json_example']}\n"
        base += f"  说明: {schema['description']}\n\n"

    base += """逻辑参考 (标准门实现):
- NAND(A, B): NOT(AND(A, B))
- NOR(A, B): NOT(OR(A, B))
- XOR(A, B): OR(AND(A, NOT(B)), AND(NOT(A), B))
- HalfAdder(A, B): SUM = XOR(A, B), CARRY = AND(A, B)

规则:
- 基础门只允许 AND、OR、NOT、INPUT、OUTPUT。严禁直接使用 XOR 等。
- 必须使用模块思维：复杂逻辑先搭建 -> DEFINE_FUNC -> SET+SAMPLE 验证 -> 通过后 CLEAR -> ADD <模块名> 复用。DEFINE_FUNC 后未经验证就 CLEAR 视为错误。
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
- 目标驱动验证：每完成一个关键子目标就用 SET+SAMPLE 或 <observe> 跑用例确认；验证失败则解释差异并继续整改。
- done 的标准：只有当你已经用 state（必要时用 TOGGLE 做测试）验证目标达成，且不需要再执行任何命令时，才输出 done=true。
- 如果用户目标需要改动画布，但你在本轮没有输出任何可执行命令，则 done 必须为 false，并给出下一步命令或说明阻碍点。
- 查看电路状态时注意：自定义模块元件在 IO 摘要中显示为 functions 列表，在完整电路状态中显示为 type="FUNCTION" 且 name 字段为模块名（如 "FullAdder"）。不要因为 IO 摘要中没有列出它们就以为添加失败。
- 如果你添加了自定义模块元件（如 FullAdder），它们会在下一轮的状态中正常出现。只需检查完整电路状态中的 elements 列表即可确认。

当前模块信息:
""" + modules_str + """

"""
    if feedback:
        base += _format_feedback_text(feedback)
    else:
        base += "当前电路状态 (含实时逻辑电平 state):\n" + compact_state_json

    # 注入 plan.md 和 summary.md 内容（如果存在）
    if plan_content:
        base += "\n\n--- 当前计划 (plan.md) ---\n" + plan_content
    if summary_content:
        base += "\n\n--- 历史摘要 (summary.md) ---\n" + summary_content

    # 注入技能文件（如果存在）
    if skills_content:
        base += "\n\n--- 累计经验技能 (skills.md) ---\n" + skills_content

    base += """

## 自学进化系统 (skills.md)

在 Agent 工作过程中，如果发现以下类型的知识，请在输出中包含一个可选的 `<skills>` 块：

**适合放入 skills.md 的知识：**
- 重复出现的 Bug 模式和根治方法
- 有明确理由的架构决策
- 项目特有的重要约定
- 多次遇到的陷阱和解决方案
- 调试常见失败模式的经验
- 框架/库的 API 特性和注意事项

**不适合放入 skills.md 的内容：**
- 当前任务的临时状态
- 特定电路的布局坐标
- 一次性的具体问题
- 个人偏好

**格式要求：**
```
<skills>
## [类别]

### Skill-新编号: 简短标题
- **Context**: 什么场景下适用
- **What**: 关键洞察/技能
- **Why**: 为什么重要
- **Example**: 具体例子（可选）
</skills>
```

输出 `<skills>` 块是完全可选的。系统会自动提取并持久化到 skills.md，供未来所有会话使用。
仅在知识足够通用、精简、有用时输出。宁缺毋滥。

你必须严格按以下 5 阶段结构输出。每轮都必须包含所有 5 个阶段：

<think>
综合分析：用户需求、计划文件(plan.md)中的TODO、摘要文件(summary.md)的历史进展、
上一轮观察结果（如有），以及当前电路状态。
明确本轮要解决什么、关键假设、可能的方案对比。不超过 200 字。
</think>
<plan>
根据 think 的分析结果，创建或更新 TODO 列表。
格式为 Markdown 任务列表，例如：
# Plan
## Objective
[本轮目标]

## Tasks
- [ ] 步骤 1
- [ ] 步骤 2
- [x] 已完成步骤

注意：这是会被保存到 plan.md 文件的内容，请包含完整的 TODO 结构。
</plan>
<build>
要执行的电路命令列表（每行一条，支持传统文本格式或 JSON 格式）。
如果本轮不需要构建，输出空内容。
</build>
<observe>
可选：用 JSON 描述测试用例，系统会自动执行并返回结果。
示例：{"cases":[{"inputs":[{"id":"A","value":0},{"id":"B","value":1}],"expect":[{"id":"SUM","value":1},{"id":"CARRY","value":0}]}]}
如果不需验证，输出空内容。
</observe>
<sum>
将本轮的思考成果、构建结果、观察结果，以及当前电路状态，压缩为简洁的文字总结。
格式为 Markdown，包含：当前状态摘要、进展、遇到的问题。
这是会被保存到 summary.md 文件的内容，请包含足够上下文以便后续轮次快速恢复。
</sum>
<answer>
给用户的简短中文说明（进展、问题、下一步）
</answer>
<done>true 或 false</done>

阶段说明:
- Think: 综合分析，不产生文件
- Plan: 输出结果会保存到 plan.md（覆盖之前内容）
- Build: 命令会被立即执行，结果在下一轮反馈
- Observe: 测试用例会被自动运行，结果在下一轮反馈
- Sum: 输出结果会保存到 summary.md（覆盖之前内容）

当你确认电路逻辑正确（通过 state 验证）且所有 TODO 完成时，done 设为 true。"""
    return base


def _call_llm_once(system_prompt, request_messages):
    def _do_call():
        protocol = _get_ai_protocol()
        if protocol == "anthropic":
            request_url = _build_api_url('/v1/messages')
            request_headers = {
                "x-api-key": get_ai_config()['api_key'],
                "anthropic-version": get_ai_config().get("anthropic_version", "2023-06-01"),
                "Content-Type": "application/json"
            }
            request_payload = {
                "model": get_ai_config()["model"],
                "system": system_prompt,
                "messages": request_messages,
                "temperature": 0.2,
                "max_tokens": int(get_ai_config().get("max_tokens", 4000)),
                "stream": False
            }
        else:
            request_url = _build_api_url('/chat/completions')
            request_headers = {
                "Authorization": f"Bearer {get_ai_config()['api_key']}",
                "Content-Type": "application/json"
            }
            request_payload = {
                "model": get_ai_config()["model"],
                "messages": [{"role": "system", "content": system_prompt}] + request_messages,
                "temperature": 0.2,
                "max_tokens": int(get_ai_config().get("max_tokens", 4000)),
                "stream": False
            }
        connect_timeout = float(get_ai_config().get("connect_timeout", 10))
        read_timeout = float(get_ai_config().get("read_timeout", 180))
        response = requests.post(
            request_url,
            headers=request_headers,
            json=request_payload,
            timeout=(connect_timeout, read_timeout)
        )
        # Retry on rate limiting (429) and server errors (5xx)
        if response.status_code == 429 or response.status_code >= 500:
            response.raise_for_status()
        # Non-retryable errors (4xx except 429) propagate immediately
        response.raise_for_status()
        payload = response.json()
        if protocol == "anthropic":
            content = payload.get("content") or []
            text = ''.join([c.get("text", "")
                           for c in content if isinstance(c, dict)])
            finish_reason = str(payload.get("stop_reason") or "")
            return text, finish_reason
        choices = payload.get("choices") or []
        if not choices:
            return "", ""
        message = choices[0].get("message") or {}
        finish_reason = str(choices[0].get("finish_reason") or "")
        return str(message.get("content") or ""), finish_reason

    retryable = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        requests.exceptions.ChunkedEncodingError,
    )
    return retry_call(_do_call, retryable_exceptions=retryable)


def _open_sse_stream(system_prompt, request_messages, thinking_mode=False):
    """Open SSE connection to LLM API. Returns (response, protocol)."""
    protocol = _get_ai_protocol()
    if protocol == "anthropic":
        request_url = _build_api_url('/v1/messages')
        request_headers = {
            "x-api-key": get_ai_config()['api_key'],
            "anthropic-version": get_ai_config().get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": get_ai_config()["model"],
            "system": system_prompt,
            "messages": request_messages,
            "temperature": 0.2,
            "max_tokens": int(get_ai_config().get("max_tokens", 4000)),
            "stream": True
        }
    else:
        request_url = _build_api_url('/chat/completions')
        request_headers = {
            "Authorization": f"Bearer {get_ai_config()['api_key']}",
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": get_ai_config()["model"],
            "messages": [{"role": "system", "content": system_prompt}] + request_messages,
            "max_tokens": int(get_ai_config().get("max_tokens", 4000)),
            "stream": True
        }
        if thinking_mode:
            request_payload["reasoning_effort"] = "high"
            request_payload["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            request_payload["temperature"] = 0.2

    connect_timeout = float(get_ai_config().get("connect_timeout", 10))
    read_timeout = float(get_ai_config().get("read_timeout", 180))
    resp = requests.post(
        request_url,
        headers=request_headers,
        json=request_payload,
        stream=True,
        timeout=(connect_timeout, read_timeout)
    )
    # Retry on rate limiting (429) and server errors (5xx)
    if resp.status_code == 429 or resp.status_code >= 500:
        resp.raise_for_status()
    resp.raise_for_status()
    return resp, protocol


def _call_llm_streaming(system_prompt, request_messages, thinking_mode=False):
    retryable = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        requests.exceptions.ChunkedEncodingError,
    )
    resp, protocol = retry_call(
        _open_sse_stream,
        args=(system_prompt, request_messages),
        kwargs={"thinking_mode": thinking_mode},
        retryable_exceptions=retryable,
    )

    finish_reason = ""
    try:
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
    except (requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError) as e:
        # Mid-stream failure: attempt one reconnection
        logger.warning("SSE stream interrupted mid-response, reconnecting: %s", e)
        try:
            resp2, _ = _open_sse_stream(
                system_prompt, request_messages, thinking_mode=thinking_mode
            )
            for raw_line in resp2.iter_lines(decode_unicode=True):
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
        except Exception as re:
            logger.warning("SSE reconnection also failed: %s", re)
            raise


def _quick_classify(user_message):
    """Quickly determine if user wants circuit work or just casual chat."""
    compact_state = circuit_manager.get_state()
    compact_json = json.dumps(_build_compact_state(
        compact_state), ensure_ascii=False, separators=(',', ':'))
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
        logger.warning("分类请求 API 错误 (HTTP %s)，默认走 circuit 模式",
                       e.response.status_code if e.response else "?")
        return "circuit"
    except Exception as e:
        logger.warning("分类请求发生未知异常 (%s: %s)，默认走 circuit 模式",
                       type(e).__name__, e)
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
        logger.warning("分类响应 JSON 解析失败 (%s)，原始响应: %.100s",
                       e, text.replace('\n', ' '))
        safe = user_message.strip().lower()
        circuit_keywords = ["add", "wire", "del", "move", "clear", "toggle", "set", "sim", "sample",
                            "define_func", "comment", "and", "or", "not", "input", "output",
                            "搭", "放", "做", "加", "连接", "删除", "移动", "清空", "验证",
                            "电路", "门", "仿真", "测试", "乘法", "加法", "模块"]
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


def call_llm_stream(user_message, max_rounds_override=None, thinking_mode=False, session_id=None):
    if not is_ai_configured():
        yield "请先在 Agent 侧边栏配置 API 参数。"
        return

    mode = _quick_classify(user_message)
    logger.info("用户消息分类: %s", mode)

    if mode == "chat":
        compact_state = circuit_manager.get_state()
        compact_json = json.dumps(_build_compact_state(
            compact_state), ensure_ascii=False, separators=(',', ':'))
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
            max_rounds = int(get_ai_config().get("agent_max_rounds", 100))
        if max_rounds < 1:
            max_rounds = 1
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
        no_progress_stop_rounds = int(get_ai_config().get(
            "agent_no_progress_stop_rounds", 30))
        if no_progress_stop_rounds < 3:
            no_progress_stop_rounds = 3
        yield STREAM_THINKING_MARKER
        yield "已进入自治执行模式：思考→计划→构建→观察→总结。\n"

        previous_feedback = None

        # 加载持久化文件（plan.md、summary.md、skills.md），实现跨会话连续性
        plan_content = _load_md_file(PLAN_FILE)
        summary_content = _load_md_file(SUMMARY_FILE)
        skills_content = _load_md_file(SKILLS_FILE)
        # 用于收集每轮的 plan/summary 内容
        plan_text_accumulator = ""
        sum_text_accumulator = ""

        for round_idx in range(1, max_rounds + 1):
            current_state = circuit_manager.get_state()
            compact_state = _build_compact_state(current_state)
            compact_state_json = json.dumps(
                compact_state, ensure_ascii=False, separators=(',', ':'))
            modules_data = circuit_manager._load_modules()
            available_modules = [
                f.get('name') for f in modules_data] if modules_data else []
            modules_str = f"可用自定义模块: {', '.join(available_modules)}" if available_modules else "当前无自定义模块"
            system_prompt = _build_autonomous_system_prompt(
                compact_state_json, modules_str,
                feedback=previous_feedback,
                plan_content=plan_content,
                summary_content=summary_content,
                skills_content=skills_content
            )
            # 记录本轮 LLM 请求
            _log_conversation("llm_request",
                              f"[Round {round_idx}] System prompt ({len(system_prompt)} chars)\nUser messages: {len(request_messages)} msgs",
                              session_id=session_id, round_num=round_idx)

            full_content = ""
            last_cmd_last_id = None
            executed_command_count = 0
            executed_success_count = 0
            command_errors = []
            command_results = []
            execution_error = ""
            commands_truncated = False
            MAX_CMDS_PER_ROUND = int(get_ai_config().get(
                "agent_max_cmds_per_round", 200))
            if MAX_CMDS_PER_ROUND < 10:
                MAX_CMDS_PER_ROUND = 10

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
                executed_success_count += int(
                    summary.get("executed_success") or 0)
                command_errors.extend(list(summary.get("errors") or []))
                command_results.extend(list(summary.get("results") or []))
                if cmd not in ("simulate",):
                    _log_conversation("command",
                                      f"{cmd} {json.dumps(params, ensure_ascii=False)} -> ok={summary.get('executed_success', 0)}",
                                      session_id=session_id, round_num=round_idx)
                if cmd == "add_element":
                    for r in (summary.get("results") or []):
                        if isinstance(r, dict) and r.get("command") == "add_element":
                            res = r.get("result")
                            if isinstance(res, dict) and res.get("id"):
                                last_cmd_last_id = res.get("id")
                                break
                if int(summary.get("executed_success") or 0) > 0 and cmd not in ("sample_outputs", "simulate"):
                    yield STREAM_STATE_CHANGED_MARKER

            def _execute_commands_text(commands_text):
                """通过单次批量调用执行文本块中的所有命令（事后回退方案）。"""
                cmds = []
                for line in commands_text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("```"):
                        continue
                    parsed = _parse_commands_payload(line)
                    cmds.extend(parsed)
                if cmds:
                    for marker in _execute_batch_and_yield(cmds):
                        yield marker

            # ═══ Stream LLM response ═══
            yield f"{ROUND_MARKER}{round_idx}\n"
            yield "---\n"

            # 流式命令执行器：实时执行 build 命令
            in_build = False
            build_outside_buf = ""
            build_commands_buf = ""
            build_cmd_buffer = []  # 已收集待批量执行的命令

            def _execute_batch_and_yield(commands):
                """在一次 _execute_commands_with_alias 调用中执行所有命令（共享 alias_map，单次保存）。"""
                nonlocal last_cmd_last_id, executed_command_count, executed_success_count, command_errors, command_results, commands_truncated
                if not commands:
                    return
                if executed_command_count >= MAX_CMDS_PER_ROUND:
                    commands_truncated = True
                    return
                # 限制为 MAX_CMDS_PER_ROUND
                batch = commands[:MAX_CMDS_PER_ROUND - executed_command_count]
                if len(batch) < len(commands):
                    commands_truncated = True
                summary = _execute_commands_with_alias(batch) or {}
                executed_cmds = len(batch)
                executed_command_count += executed_cmds
                executed_success_count += int(
                    summary.get("executed_success") or 0)
                command_errors.extend(list(summary.get("errors") or []))
                command_results.extend(list(summary.get("results") or []))
                # 从结果中更新 last_cmd_last_id
                for r in summary.get("results") or []:
                    if isinstance(r, dict) and r.get("command") == "add_element":
                        res = r.get("result")
                        if isinstance(res, dict) and res.get("id"):
                            last_cmd_last_id = res.get("id")
                # 生成 STATE_CHANGED 标记（触发前端画布更新）
                if executed_cmds > 0 and summary.get("executed_success", 0) > 0:
                    yield STREAM_STATE_CHANGED_MARKER
                # 记录每条命令
                for r in summary.get("results") or []:
                    cmd_name = r.get("command", "?")
                    _log_conversation(
                        "command", f"{cmd_name} -> ok", session_id=session_id, round_num=round_idx)
                for e in summary.get("errors") or []:
                    _log_conversation(
                        "command", f"{e.get('command', '?')}: {e.get('error', '?')} -> fail", session_id=session_id, round_num=round_idx)

            def _feed_stream_commands(text):
                """流式执行器：收集命令，在段落关闭时批量执行。"""
                nonlocal in_build, build_outside_buf, build_commands_buf, build_cmd_buffer
                remaining = text or ""
                while remaining:
                    if not in_build:
                        build_outside_buf += remaining
                        # 检查开始标签
                        bpos = build_outside_buf.lower().find("<build>")
                        cpos = build_outside_buf.lower().find("<commands>")
                        positions = [p for p in (bpos, cpos) if p != -1]
                        if not positions:
                            if len(build_outside_buf) > 200:
                                build_outside_buf = build_outside_buf[-200:]
                            return
                        pos = min(positions)
                        tag_len = 7 if pos == bpos else 10  # <build>=7个字符，<commands>=10个字符
                        build_outside_buf = build_outside_buf[pos + tag_len:]
                        in_build = True
                        remaining = build_outside_buf
                        build_outside_buf = ""
                        continue

                    # 在 build 段内：收集行，暂不执行
                    build_commands_buf += remaining
                    remaining = ""

                    # 检查结束标签
                    bclose = build_commands_buf.lower().find("</build>")
                    cclose = build_commands_buf.lower().find("</commands>")
                    cpositions = [p for p in (bclose, cclose) if p != -1]

                    if cpositions:
                        close_pos = min(cpositions)
                        close_len = 8 if close_pos == bclose else 11  # </build>=8个字符，</commands>=11个字符
                        segment = build_commands_buf[:close_pos]
                        remainder = build_commands_buf[close_pos + close_len:]
                        build_commands_buf = ""
                        in_build = False
                        # 解析段落中的所有行
                        for line in segment.splitlines():
                            line = line.strip()
                            if not line or line.startswith("```"):
                                continue
                            parsed = _parse_commands_payload(line)
                            build_cmd_buffer.extend(parsed)
                        # 一次性批量执行所有已收集的命令
                        if build_cmd_buffer:
                            for marker in _execute_batch_and_yield(build_cmd_buffer):
                                yield marker
                            build_cmd_buffer = []
                        remaining = remainder
                        continue

                    # 尚无结束标签：解析完整行并添加到缓冲区
                    if "\n" not in build_commands_buf:
                        return
                    lines = build_commands_buf.split("\n")
                    build_commands_buf = lines[-1]  # keep incomplete line
                    for raw_line in lines[:-1]:
                        line = raw_line.strip()
                        if not line or line.startswith("```"):
                            continue
                        parsed = _parse_commands_payload(line)
                        build_cmd_buffer.extend(parsed)
                    return

            try:
                for chunk, fr in _call_llm_streaming(system_prompt, request_messages, thinking_mode=thinking_mode):
                    if fr:
                        finish_reason = fr
                    if chunk:
                        full_content += chunk
                        yield chunk
                        # 在流式输出期间实时执行命令
                        for marker in _feed_stream_commands(chunk):
                            if marker is not None:
                                yield marker
            except Exception as e:
                execution_error = str(e)
                logger.error("[Round %d] Stream error: %s", round_idx, e)
                yield f"[第{round_idx}轮调用异常] {execution_error}\n"

            # 执行未关闭的 build 段中剩余的命令（流在构建中结束）
            if build_cmd_buffer:
                logger.info("[Round %d] Executing %d remaining build commands (unclosed section)", round_idx, len(
                    build_cmd_buffer))
                for marker in _execute_batch_and_yield(build_cmd_buffer):
                    if marker is not None:
                        yield marker
                build_cmd_buffer = []

            if finish_reason in {"length", "max_tokens"}:
                request_messages.append({
                    "role": "user",
                    "content": "系统：你的上轮输出因达到 token 上限而被截断。请在回复中保持精简，优先输出命令。"
                })

            request_messages.append(
                {"role": "assistant", "content": full_content})
            _log_conversation("llm_response",
                              f"[Round {round_idx}] Response ({len(full_content)} chars)\n{full_content[:500]}",
                              session_id=session_id, round_num=round_idx)

            # ═══ 从完整响应中事后提取所有段落 ═══
            # 提取新 5 阶段段落（兼容旧格式）
            build_text = _extract_tag_text(
                full_content, "build") or _extract_tag_text(full_content, "commands")
            observe_text = _extract_tag_text(
                full_content, "observe") or _extract_tag_text(full_content, "verify")
            raw_plan_text = _extract_tag_text(full_content, "plan")
            raw_sum_text = _extract_tag_text(full_content, "sum")
            answer_text = _extract_tag_text(full_content, "answer")
            done_flag = _is_done_response(full_content)

            # 执行 build 命令（流式未执行时的事后回退）
            streaming_executed = executed_command_count
            if build_text.strip():
                if streaming_executed == 0:
                    logger.info("[Round %d] Executing %d build lines (post-hoc fallback)",
                                round_idx, len(build_text.splitlines()))
                    for marker in _execute_commands_text(build_text):
                        if marker is not None:
                            yield marker
                else:
                    logger.info(
                        "[Round %d] %d commands already executed during streaming, skipping post-hoc", round_idx, streaming_executed)
                aggregated_commands.append(build_text)
            elif streaming_executed > 0:
                logger.info(
                    "[Round %d] %d commands executed during streaming (no post-hoc needed)", round_idx, streaming_executed)
            else:
                logger.info(
                    "[Round %d] No build/commands content found", round_idx)

            # 保存 plan.md 和 summary.md
            if raw_plan_text.strip():
                _atomic_write_md(PLAN_FILE, raw_plan_text.strip())
                plan_content = raw_plan_text.strip()
                logger.info("已更新 plan.md")
            if raw_sum_text.strip():
                _atomic_write_md(SUMMARY_FILE, raw_sum_text.strip())
                summary_content = raw_sum_text.strip()
                logger.info("已更新 summary.md")

            # 自学进化：提取 <skills> 块并合并到 skills.md
            raw_skills_text = _extract_tag_text(full_content, "skills")
            if raw_skills_text and raw_skills_text.strip():
                logger.info(
                    "[Round %d] 发现 <skills> 块，尝试合并到 skills.md", round_idx)
                existing_skills = _load_md_file(SKILLS_FILE)
                merged = _merge_skills(raw_skills_text, existing_skills)
                if merged is not None:
                    _atomic_write_md(SKILLS_FILE, merged)
                    skills_content = merged
                    logger.info("已更新 skills.md (自学进化)")
                else:
                    logger.info("skills.md 无变化（技能已存在或格式无效）")

            # answer 回退
            if not answer_text:
                answer_text = "已完成本轮处理。"
            final_answer_text = answer_text

            # 准备 verify/observe 对象
            verify_obj = _extract_verify_payload_from_text(
                observe_text) if observe_text else None

            after_state = circuit_manager.get_state()
            compact_after_state = _build_compact_state(after_state)
            state_fingerprint = json.dumps(
                compact_after_state, ensure_ascii=False, separators=(',', ':'))
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
            function_count = len(circuit_manager._load_modules())
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
                if same_error_rounds >= 5:
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
                msg = "系统检查：本轮部分命令执行失败，请修复后继续。\n" + \
                    ("\n".join(lines) if lines else "")
                request_messages.append({"role": "user", "content": msg})

            sample_payloads = [r.get("result") for r in command_results if isinstance(
                r, dict) and r.get("command") == "sample_outputs"]
            if sample_payloads:
                latest = sample_payloads[-1]
                request_messages.append(
                    {"role": "user", "content": f"系统采样结果：{json.dumps(latest, ensure_ascii=False, separators=(',', ':'))}"})
            else:
                request_messages.append(
                    {"role": "user", "content": f"系统IO摘要：{json.dumps(io_summary, ensure_ascii=False, separators=(',', ':'))}"})

            verify_report = None
            if verify_obj is not None:
                verify_report = _run_verify_cases(verify_obj)
                if verify_report is None:
                    request_messages.append(
                        {"role": "user", "content": "系统验证失败：observe 内容无法解析或为空。请输出合法 JSON 并重试。"})
                    done_flag = False
                else:
                    report_text = json.dumps(
                        verify_report, ensure_ascii=False, separators=(',', ':'))
                    request_messages.append(
                        {"role": "user", "content": f"系统验证报告：{report_text}"})
                    if verify_report.get("failed", 0) > 0:
                        done_flag = False

            # 构建下一轮反馈
            state_diff = _compute_state_diff(
                current_state, after_state) if round_idx > 1 else None
            previous_feedback = {
                "execution": {
                    "command_count": executed_command_count,
                    "success_count": executed_success_count,
                    "errors": command_errors[:5]
                },
                "state_diff": state_diff,
                "verify_results": verify_report
            }

            if done_flag:
                _log_conversation(
                    "system", f"[Round {round_idx}] Agent done: {final_answer_text[:200]}", session_id=session_id, round_num=round_idx)
                break

            if cycle_rounds >= 20:
                final_answer_text = (
                    "检测到电路状态在少数几个状态之间循环变化（可能反复 TOGGLE 或反复增删无效）。"
                    "为避免无效调用，我已停止自治循环。你可以指定更明确的目标或允许我先重置关键输入再测试。"
                )
                _log_conversation(
                    "system", f"Loop terminated: cycle detected after {round_idx} rounds", session_id=session_id, round_num=round_idx)
                break

            if no_progress_rounds >= no_progress_stop_rounds:
                _log_conversation(
                    "system", f"Loop terminated: no progress after {round_idx} rounds", session_id=session_id, round_num=round_idx)
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

            if OverflowDetector().should_compact(request_messages):
                request_messages = ContextCompactor().compact(request_messages)

        yield STREAM_ANSWER_MARKER
        final_output = final_answer_text.strip() if final_answer_text else "已完成处理。"
        if aggregated_commands:
            merged_commands = "\n".join(
                [c for c in aggregated_commands if c.strip()]).strip()
            final_output += f"\n<commands>\n{merged_commands}\n</commands>"
        else:
            final_output += "\n<commands>\n[]\n</commands>"
        yield final_output

        assistant_memory_text = _strip_commands_from_reply(final_output)
        _append_chat_memory("user", user_message)
        _append_chat_memory("assistant", assistant_memory_text)

        if finish_reason in {"length", "max_tokens"}:
            yield "\n[系统] 输出达到 max_tokens 上限，思考或回复可能被截断。可在 Agent 侧边栏配置中调大 max_tokens。"

    except Exception as e:
        yield f"调用 AI 失败: {str(e)}"


@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    """列出所有历史对话"""
    import os
    try:
        files = []
        for fname in os.listdir(LOG_DIR):
            if not fname.startswith('conversation_') or not fname.endswith('.jsonl'):
                continue
            fpath = os.path.join(LOG_DIR, fname)
            # 从文件名解析: conversation_{date}_{session_id}.jsonl
            parts = fname.replace('.jsonl', '').split('_', 2)
            date_str = parts[1] if len(parts) > 1 else ''
            sess_id = parts[2] if len(parts) > 2 else ''
            # 读取第一行获取预览
            preview = ''
            msg_count = 0
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    for line in f:
                        msg_count += 1
                        if not preview and line.strip():
                            import json
                            try:
                                entry = json.loads(line)
                                content = entry.get('content', '')
                                if content:
                                    preview = content[:80]
                            except:
                                pass
            except:
                pass
            files.append({
                'session_id': sess_id,
                'date': date_str,
                'message_count': msg_count,
                'preview': preview,
                'filename': fname,
            })
        # 按日期降序排列
        files.sort(key=lambda x: x['date'], reverse=True)
        return jsonify({'conversations': files})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/conversations/<session_id>', methods=['GET'])
def get_conversation(session_id):
    """读取指定对话的消息"""
    import os
    try:
        for fname in os.listdir(LOG_DIR):
            if session_id in fname and fname.endswith('.jsonl'):
                fpath = os.path.join(LOG_DIR, fname)
                messages = []
                with open(fpath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            import json
                            messages.append(json.loads(line))
                return jsonify({'messages': messages, 'filename': fname})
        return jsonify({'status': 'error', 'message': '对话未找到'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    聊天接口：流式输出
    """
    session_id = uuid.uuid4().hex[:12]
    try:
        data = request.json
        message = data.get('message', '')
        max_rounds = data.get('max_rounds', None)
        thinking_mode = data.get('thinking_mode', False)
        logger.info("/api/chat 接收到的 max_rounds=%s, thinking_mode=%s",
                    max_rounds, thinking_mode)
        _log_conversation("user", message, session_id=session_id)

        full_response = [""]

        def generate():
            yield f"__TC_SESSION__:{session_id}\n"
            for chunk in call_llm_stream(message, max_rounds_override=max_rounds, thinking_mode=thinking_mode, session_id=session_id):
                full_response[0] += chunk
                yield chunk
            # 流式输出后，记录助手的完整回复
            _log_conversation("assistant", full_response[0], session_id=session_id)

        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        _log_conversation("system", f"Chat error: {str(e)}", session_id=session_id)
        return jsonify({'status': 'error', 'message': str(e)}), 500


def fallback_chat(message, error_msg):
    """
    回退逻辑：当 LLM 不可用时，使用关键词匹配或报错
    """
    message = message.lower()
    commands_executed = []
    reply = ""

    # 如果 API Key 没填，提示用户，但仍然尝试处理简单指令
    is_config_error = not is_ai_configured()

    if "清空" in message or "clear" in message:
        execute_circuit_command('clear_circuit', {})
        reply = "好的，我已经清空了所有电路。"
        commands_executed.append({'command': 'clear_circuit'})
    elif "与门" in message:
        res = execute_circuit_command(
            'add_element', {'type': 'AND', 'x': 100, 'y': 100})
        reply = f"已为您添加了一个与门。"
        commands_executed.append({'command': 'add_element', 'type': 'AND'})
    else:
        if is_config_error:
            reply = "⚠️ 您尚未在 app.py 中配置 get_ai_config()['api_key']。目前我只能处理简单的指令如“添加与门”、“清空画布”。"
        else:
            reply = f"抱歉，调用 AI 时遇到了错误: {error_msg}。"

    return jsonify({
        'status': 'success',
        'reply': reply,
        'commands_executed': commands_executed,
        'config_needed': is_config_error
    })


@app.route('/api/save-module', methods=['POST', 'OPTIONS'])
def save_module():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        new_module = request.json
        # 读取现有的模块
        modules_data = {'modules': []}
        if os.path.exists(MODULES_DATA_FILE):
            try:
                with open(MODULES_DATA_FILE, 'r', encoding='utf-8') as f:
                    modules_data = json.load(f)
            except json.JSONDecodeError:
                modules_data = {'modules': []}

        # 保存新模块
        modules_data['modules'].append(new_module)

        _atomic_write_json(MODULES_DATA_FILE, modules_data)
        logger.info("模块已保存到: %s", MODULES_DATA_FILE)
        return jsonify({'status': 'success', 'message': 'Module saved successfully'})
    except Exception as e:
        logger.error("保存模块失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/save-modules', methods=['POST', 'OPTIONS'])
def save_modules():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        _atomic_write_json(MODULES_DATA_FILE, data)
        logger.info("模块列表已保存到: %s", MODULES_DATA_FILE)
        return jsonify({'status': 'success', 'message': 'Modules saved successfully'})
    except Exception as e:
        logger.error("保存模块列表失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/load-modules', methods=['GET', 'OPTIONS'])
def load_modules():
    # 处理OPTIONS预检请求
    if request.method == 'OPTIONS':
        return '', 200
    try:
        if os.path.exists(MODULES_DATA_FILE):
            try:
                with open(MODULES_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                logger.warning("模块数据文件损坏，使用空结构: %s", MODULES_DATA_FILE)
                data = {'modules': []}
            logger.info("模块数据已加载，包含 %d 个模块", len(data.get('modules', [])))
            return jsonify(data)
        else:
            return jsonify({'modules': []})
    except Exception as e:
        logger.error("加载模块数据失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Arduino 导出 ──────────────────────────────────────────────────────


def _format_upload_error(raw_err: str, port: str) -> str:
    """将 arduino-cli 上传错误格式化为用户友好的中文提示。

    常见可恢复错误（端口被占用、权限被拒）建议重试，其他错误保持原文。
    """
    err_lower = raw_err.lower()

    if "cannot open port" in err_lower or "unable to open port" in err_lower:
        return (
            f"上传到 {port} 失败：端口被占用或拒绝访问。\n"
            "可能的原因：\n"
            "  1. 其他程序（如 Arduino IDE、串口监视器）正在使用该端口\n"
            "  2. USB 线松动或接触不良\n"
            "  3. 驱动问题\n\n"
            "请关闭占用端口的程序，检查 USB 连接后重试。\n"
            "原错误信息：\n"
            f"{raw_err.strip()}"
        )

    if ("permission" in err_lower and "denied" in err_lower) or \
       ("access" in err_lower and "denied" in err_lower):
        return (
            f"上传到 {port} 失败：权限不足。\n"
            "  Windows：请以管理员身份运行本程序\n"
            "  Linux：  将用户添加到 dialout 组：sudo usermod -a -G dialout $USER\n"
            "  macOS：  检查 /dev/tty.* 权限\n\n"
            "原错误信息：\n"
            f"{raw_err.strip()}"
        )

    if "timeout" in err_lower:
        return (
            f"上传到 {port} 超时。\n"
            "请检查 USB 连接是否正常，然后重试。\n\n"
            "原错误信息：\n"
            f"{raw_err.strip()}"
        )

    # 兜底：保持原文，加一句重试建议
    return f"上传失败（{port}）：\n{raw_err.strip()}\n\n请检查连接后重试。"


@app.route('/api/export-arduino', methods=['POST'])
def export_arduino():
    """一键将当前电路转写为 Arduino 代码。

    Request body (optional JSON):
        {"upload": false, "port": "COM3"}

    Returns:
        JSON with generated sketch code and optional upload status.
    """
    try:
        body = request.get_json(silent=True) or {}
        should_upload = body.get("upload", False)
        port = body.get("port", "")

        # ── 读取当前电路数据 ──────────────────────────────────────────
        circuit_data = circuit_manager.get_state()
        modules_data = {}
        if os.path.exists(MODULES_DATA_FILE):
            try:
                with open(MODULES_DATA_FILE, "r", encoding="utf-8") as f:
                    modules_data = json.load(f)
            except Exception:
                modules_data = {}

        # ── 解析并生成代码 ─────────────────────────────────────────────
        from turing_to_arduino.circuit_parser import parse_circuit
        from turing_to_arduino.code_generator import generate_arduino_sketch

        dag = parse_circuit(circuit_data, modules_data)
        sketch = generate_arduino_sketch(dag)

        result = {
            "status": "success",
            "sketch": sketch,
            "inputs": len(dag.inputs),
            "outputs": len(dag.outputs),
            "gates": len(dag.gates),
        }

        # ── 可选：编译上传 ────────────────────────────────────────────
        if should_upload:
            from turing_to_arduino.uploader import (
                check_arduino_cli,
                compile_sketch,
                upload_sketch,
                detect_boards,
            )

            if not check_arduino_cli():
                from turing_to_arduino.uploader import _get_arduino_cli_install_guide
                return jsonify({
                    "status": "error",
                    "message": "arduino-cli not found.\n"
                               f"{_get_arduino_cli_install_guide()}",
                    "sketch": sketch,
                }), 400

            import tempfile
            sketch_dir = tempfile.mkdtemp(prefix="tc_arduino_")
            # Arduino CLI requires .ino filename == parent directory name
            sketch_name = os.path.basename(sketch_dir) + ".ino"
            sketch_path = os.path.join(sketch_dir, sketch_name)
            with open(sketch_path, "w", encoding="utf-8") as f:
                f.write(sketch)

            # ── 自动检测端口 ──────────────────────────────────────
            if not port:
                boards = detect_boards()
                detected_port = None
                if isinstance(boards, list):
                    for b in boards:
                        addr = b.get("address", "")
                        if addr:
                            detected_port = addr
                            break
                if not detected_port:
                    return jsonify({
                        "status": "error",
                        "message": "未检测到连接的 Arduino 板子。\n请确认 USB 已连接。",
                        "sketch": sketch,
                    }), 400
                port = detected_port

            compile_ok, _, compile_err = compile_sketch(sketch_dir)
            if not compile_ok:
                return jsonify({
                    "status": "error",
                    "message": f"Compilation failed:\n{compile_err}",
                    "sketch": sketch,
                }), 500

            max_retries = 3
            upload_ok = False
            upload_err = ""
            for attempt in range(1, max_retries + 1):
                upload_ok, _, upload_err = upload_sketch(sketch_dir, port)
                if upload_ok:
                    break
                # 仅对端口争用类错误自动重试
                err_lower = (upload_err or "").lower()
                is_port_contention = (
                    "cannot open port" in err_lower or
                    "unable to open port" in err_lower or
                    ("access" in err_lower and "denied" in err_lower) or
                    ("permission" in err_lower and "denied" in err_lower)
                )
                if not is_port_contention or attempt >= max_retries:
                    break
                import time
                time.sleep(1.5)

            if not upload_ok:
                friendly_msg = _format_upload_error(upload_err, port)
                return jsonify({
                    "status": "error",
                    "message": friendly_msg,
                    "error_detail": upload_err,
                    "sketch": sketch,
                }), 500

            import shutil
            try:
                shutil.rmtree(sketch_dir)
            except Exception:
                pass

            result["uploaded"] = True
            result["port"] = port

        return jsonify(result)

    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error("导出 Arduino 失败: %s", e)
        return jsonify({"status": "error", "message": f"Export failed: {e}"}), 500


@app.route('/api/detect-boards', methods=['GET'])
def detect_boards_api():
    """Detect connected Arduino boards."""
    try:
        from turing_to_arduino.uploader import detect_boards
        boards = detect_boards()
        # detect_boards() returns normalized format [{address, label, name, fqbn}, ...]
        return jsonify({"boards": boards})
    except Exception as e:
        logger.error("检测 Arduino 板子失败: %s", e)
        return jsonify({"boards": [], "error": str(e)})


@app.route('/api/subagent', methods=['POST'])
def api_create_subagent():
    """Create a new subagent task for parallel circuit execution."""
    try:
        data = request.json
        if not data or 'goal' not in data:
            return jsonify({'status': 'error', 'message': 'Missing goal'}), 400
        goal = data['goal']
        snapshot = data.get('circuit_snapshot')
        if snapshot is None:
            snapshot = circuit_manager.export_snapshot()
        task_id = subagent_manager.create(goal, snapshot)
        return jsonify({'subagent_id': task_id, 'status': 'running'})
    except Exception as e:
        logger.error("创建子代理失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/subagent/<task_id>', methods=['GET'])
def api_get_subagent(task_id):
    """Query subagent task status and result."""
    try:
        status = subagent_manager.get_status(task_id)
        if status is None:
            return jsonify({'status': 'error', 'message': 'Subagent not found'}), 404
        return jsonify(status)
    except Exception as e:
        logger.error("查询子代理状态失败: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    logger.info("电路设计应用启动中...")
    logger.info("电路数据文件路径: %s", CIRCUIT_DATA_FILE)
    logger.info("模块数据文件路径: %s", MODULES_DATA_FILE)
    logger.info("打开软件: http://localhost:5000")
    # 禁用Flask的开发服务器banner
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    app.run(debug=False, host='0.0.0.0', port=5000)
