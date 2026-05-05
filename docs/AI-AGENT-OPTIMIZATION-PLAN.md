# AI Agent 优化方案

> 基于对现代 AI Coding Agent（如 Claude Code、Cursor、GitHub Copilot 等）成功模式的逆向分析，
  对当前项目 Agent 系统的架构差距分析与改造计划。

---

## 一、现状分析

### 1.1 现有架构概览

```
用户输入
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  call_llm_stream()                                  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  _quick_classify() → circuit / chat           │  │
│  └───────────────────────────────────────────────┘  │
│           │ circuit                                 │
│           ▼                                         │
│  ┌───────────────────────────────────────────────┐  │
│  │  Agent Loop (多轮 Plan→Execute→Check)         │  │
│  │                                                │  │
│  │  Round N:                                     │  │
│  │    1. 读取电路状态 → 构建 system prompt        │  │
│  │    2. LLM 流式输出（<plan>/<commands>/...）    │  │
│  │    3. 实时解析 <commands> 逐条执行             │  │
│  │    4. 检查结果 → done? → 继续/停止             │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 1.2 已有能力（已做对的部分）

| 能力 | 状态 | 位置 |
|---|---|---|
| Agent 循环（Plan→Execute→Check→Continue） | ✅ 已有 | `call_llm_stream()` |
| 结构化输出格式（`<plan>`, `<commands>`, `<verify>`, `<done>`） | ✅ 已有 | `_build_autonomous_system_prompt()` |
| 电路状态注入（每轮 LLM 可见） | ✅ 已有 | system prompt 尾部 |
| 流式输出（SSE） | ✅ 已有 | 通过 `yield` 逐块输出 |
| 命令执行与画布刷新 | ✅ 已有 | `_execute_commands_with_alias()` + 前端 `loadFromServer()` |
| 震荡检测（ABAB 循环） | ✅ 已有 | `_is_abab_cycle()` |
| 思考/输出分离 | ✅ 已有 | `__TC_THINKING__` / `__TC_ANSWER__` 标记 |
| 别名系统（ID/alias 双引用） | ✅ 已有 | `_bind_alias()` + `_resolve_element_ref()` |

---

## 二、差距分析

### 差距 1：工具调用方式 —— 文本解析 vs 结构化 Tool Use

**现状：**

AI 输出纯文本命令到 `<commands>` 块中，后端用 `_parse_commands_payload()` 做逐行正则解析：

```
ADD AND 240 60 g1
WIRE g1 0 g2 1
```

解析依赖精确的空格分隔、不稳定的 `_clean_token()` 清洗，遇到格式偏差时 `except: continue` 静默跳过。

**现代 AI Agent 的做法：**

每条工具都有明确的名称、参数类型、描述和示例。模型输出 JSON 结构：

```json
{"tool": "add_element", "params": {"type": "AND", "x": 240, "y": 60, "alias": "g1"}}
```

优势：
- **模型更易生成**：JSON 结构天然匹配 LLM 训练数据中的 function calling 分布
- **解析零歧义**：`json.loads()` 即可，无需清洗/修复
- **参数校验自动**：类型、必填/可选、枚举值均可程序化校验
- **向后兼容**：JSON + text 双格式，同一系统共存

### 差距 2：反馈机制 —— 全量状态转储 vs 观察-响应循环

**现状：**

每轮系统提示词中都注入**完整的电路状态 JSON**（含全部元件坐标、端口细节、导线列表）：

```python
system_prompt += "当前电路状态:\n" + compact_state_json
```

这样做的问题是：
- **Token 浪费**：每轮携带大量冗余信息（坐标、端口列表等）
- **信噪比低**：AI 需要在大量数据中自行找出"这轮发生了什么变化"
- **无执行结果反馈**：命令执行成功/失败的信息没有返回给 AI，AI 只能通过状态推断

**现代 AI Agent 的做法：**

```
--- 本轮操作结果 ---
成功执行: 5 条命令
新增元件: and1(ID:abc123) @ (240,60), or2(ID:def456) @ (240,140)
新增连线: and1.out0 → or2.in0
错误: 无

当前 IO 摘要:
  输入: A=0, B=1
  输出: SUM=1, CARRY=0
```

优势：
- **Token 大幅节省**：从稳态开始后只传递变化
- **信息清晰**：AI 直接知道发生了什么
- **可追溯错误**：执行错误显式暴露，AI 可针对性修复

### 差距 3：验证方式 —— 手工文本 vs 自动执行

**现状：**

AI 可以在输出中包含 `<verify>` 块来描述测试用例，但框架不会自动执行：

```xml
<verify>
{"cases":[{"inputs":[{"id":"A","value":0},{"id":"B","value":1}],
           "expect":[{"id":"SUM","value":1},{"id":"CARRY","value":0}]}]}
</verify>
```

AI 只能自己用 `SET` + `SAMPLE` 在电路上实际操作来验证，这一方面增加了执行轮次，另一方面验证过程中会污染电路状态。

**现代 AI Agent 的做法：**

AI 定义测试用例 → 框架拍照电路状态 → 自动注入输入 → 运行仿真 → 比对输出 → 恢复原始状态 → 返回结果。

```
--- 测试验证结果 ---
测试 0: ✅ 通过
  A=0, B=1 → SUM=1 (期望=1) ✅, CARRY=0 (期望=0) ✅
测试 1: ❌ 失败
  A=1, B=1 → SUM=0 (期望=0) ✅, CARRY=0 (期望=1) ❌
```

### 差距 4：记忆管理（次要）

**现状：** 对话历史无限追加，无摘要/裁剪。长期会话会导致 token 膨胀。

**现代做法：** 滑动窗口（保留最近 N 轮）+ 历史摘要压缩。

---

## 三、改造方案

### Phase 1：结构化 Tool Use

**目标：** 在保留文本命令向后兼容的前提下，引入 JSON 格式的结构化工具调用。

#### 3.1.1 工具定义

新增常量 `TOOL_DEFINITIONS`，每条工具包含：

```python
TOOL_DEFINITIONS = [
    {
        "tool": "add_element",
        "description": "添加一个元件到电路",
        "params": [
            {"name": "type", "type": "enum", "enum_values": ["AND", "OR", "NOT", "INPUT", "OUTPUT", "FUNCTION"], "required": True, "description": "元件类型"},
            {"name": "x", "type": "number", "required": True, "description": "X 坐标"},
            {"name": "y", "type": "number", "required": True, "description": "Y 坐标"},
            {"name": "alias", "type": "string", "required": False, "description": "别名，用于后续引用"}
        ],
        "text_example": "ADD AND 240 60 g1",
        "json_example": '{"tool": "add_element", "params": {"type": "AND", "x": 240, "y": 60, "alias": "g1"}}'
    },
    # ... 其余工具
]
```

#### 3.1.2 解析器改造

`_parse_commands_payload()` 增加 JSON 检测分支：

```python
def _parse_commands_payload(commands_str):
    commands = []
    for line in commands_str.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # JSON 格式优先检测
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

        # 原有文本解析（向后兼容）
        parts = [...]
        # ... 原有 ADD/WIRE/DEL/... 解析逻辑
    return commands
```

#### 3.1.3 系统提示词改造

将当前系统提示词中纯文本的"可用指令集"替换为结构化表格，每种工具同时展示 JSON 和 text 两种格式：

```
可用工具:

1. add_element — 添加元件
   参数: type(AND|OR|NOT|INPUT|OUTPUT|FUNCTION), x(number), y(number), alias(string, 可选)
   JSON: {"tool": "add_element", "params": {"type": "AND", "x": 240, "y": 60, "alias": "g1"}}
   文本: ADD AND 240 60 g1

2. add_wire — 连接两个元件
   参数: from_ref(string), from_port_idx(int), to_ref(string), to_port_idx(int)
   JSON: {"tool": "add_wire", "params": {"from_ref": "g1", "from_port_idx": 0, "to_ref": "g2", "to_port_idx": 1}}
   文本: WIRE g1 0 g2 1

...
```

---

### Phase 2：动作反馈 + State Diff

**目标：** 将全量状态注入替换为差异反馈。

#### 3.2.1 State Diff 计算

```python
def _compute_state_diff(old_state, new_state):
    old_el = {e["id"]: e for e in old_state.get("elements", [])}
    new_el = {e["id"]: e for e in new_state.get("elements", [])}

    added = []
    for eid, e in new_el.items():
        if eid not in old_el:
            added.append({"id": e["id"], "type": e["type"], "alias": e.get("alias"), "pos": [e.get("x"), e.get("y")]})

    removed = [{"id": e["id"], "type": e["type"]} for eid, e in old_el.items() if eid not in new_el]

    changed = []
    for eid, e in new_el.items():
        if eid in old_el:
            o = old_el[eid]
            if e.get("x") != o.get("x") or e.get("y") != o.get("y"):
                changed.append({"id": eid, "type": "position", "from": [o.get("x"), o.get("y")], "to": [e.get("x"), e.get("y")]})
            if e.get("state") != o.get("state"):
                changed.append({"id": eid, "type": "state", "from": o.get("state"), "to": e.get("state")})

    old_wires = {(w["start"]["elementId"], w["end"]["elementId"]): w["id"] for w in old_state.get("wires", []) if "start" in w and "end" in w}
    new_wires = {(w["start"]["elementId"], w["end"]["elementId"]): w["id"] for w in new_state.get("wires", []) if "start" in w and "end" in w}

    wires_added = []
    for conn, wid in new_wires.items():
        if conn not in old_wires:
            wires_added.append({"id": wid, "from": conn[0], "to": conn[1]})

    wires_removed = [{"id": wid, "from": conn[0], "to": conn[1]} for conn, wid in old_wires.items() if conn not in new_wires]

    return {
        "elements_added": added,
        "elements_removed": removed,
        "elements_changed": changed,
        "wires_added": wires_added,
        "wires_removed": wires_removed,
        "io_summary": _build_io_summary(new_state)
    }
```

#### 3.2.2 Agent 循环改造

`call_llm_stream()` 中修改 system prompt 构建逻辑：

```python
previous_state = None

for round_idx in range(1, max_rounds + 1):
    current_state = circuit_manager.get_state()

    if round_idx == 1:
        # 首轮：提供全量状态
        system_prompt = _build_autonomous_system_prompt(
            compact_state_json=compact_state_json,
            functions_str=functions_str
        )
    else:
        # 后续轮次：提供 diff 反馈
        state_diff = _compute_state_diff(previous_state, current_state)
        # 也携带本轮命令执行摘要
        execution_summary = {
            "total_commands": executed_command_count,
            "success_count": executed_success_count,
            "errors": command_errors,
            "results": command_results
        }
        system_prompt = _build_autonomous_system_prompt(
            compact_state_json=None,      # 不传全量状态
            functions_str=functions_str,
            state_diff=state_diff,
            execution_summary=execution_summary
        )

    previous_state = copy.deepcopy(current_state)
    # ... 原有 LLM 调用和执行逻辑 ...
```

#### 3.2.3 系统提示词模板变化

**首轮：**
```
当前电路状态:
{"elements": [...], "wires": [...]}
```

**后续轮次：**
```
--- 第 N 轮操作反馈 ---
执行摘要: 5/5 命令成功执行
错误: 无

状态变更:
  + 新增元件: and1(ID:abc123) @ (240,60)
  + 新增连线: and1.out0 → or2.in0
  ~ 状态改变: or2.state: 0 → 1 (仿真传播)

当前 IO 摘要:
  输入: A=0, B=1
  输出: SUM=1, CARRY=0
```

---

### Phase 3：验证框架

**目标：** 自动执行 AI 定义的测试用例并返回结果。

#### 3.3.1 验证执行函数

```python
def _run_verify_cases(cases_json):
    """
    输入: JSON 字符串或 Python 对象，格式：
    [{"inputs": [{"id": "A", "value": 0}, ...],
      "expect": [{"id": "SUM", "value": 1}, ...]}]

    返回: [{"case": 0, "passed": True, "details": [...]}]
    """
    if isinstance(cases_json, str):
        cases = json.loads(cases_json)
    else:
        cases = cases_json

    if not isinstance(cases, list):
        raise ValueError("verify cases must be a list")

    snapshot = copy.deepcopy(circuit_manager.get_state())
    results = []

    try:
        for i, case in enumerate(cases):
            # 设置输入
            for inp in case.get("inputs", []):
                try:
                    circuit_manager.set_input(inp["id"], inp["value"])
                except ValueError as e:
                    results.append({
                        "case": i, "passed": False,
                        "error": f"SET 失败: {e}",
                        "details": []
                    })
                    continue

            # 仿真
            circuit_manager.simulate()

            # 采样输出
            try:
                actual = circuit_manager.sample_outputs()
            except Exception as e:
                results.append({
                    "case": i, "passed": False,
                    "error": f"SAMPLE 失败: {e}",
                    "details": []
                })
                continue

            # 逐一对比期望值
            details = []
            for exp in case.get("expect", []):
                act = next(
                    (o for o in actual.get("outputs", []) if o["id"] == exp["id"]),
                    None
                )
                if act is None:
                    act_state = None
                else:
                    act_state = act.get("state", None)

                expected_state = bool(exp["value"])
                match = (act_state == expected_state)

                details.append({
                    "id": exp["id"],
                    "expected": expected_state,
                    "actual": act_state,
                    "match": match
                })

            results.append({
                "case": i,
                "passed": all(d["match"] for d in details),
                "details": details
            })
    finally:
        # 恢复原始状态（关键！避免验证过程污染用户电路）
        circuit_manager._save_data(snapshot)

    return results
```

#### 3.3.2 注入验证结果

在每轮命令执行完成后、构建下一轮系统提示词之前：

```python
# 解析 AI 本轮输出中的 <verify> 块
verify_match = re.search(r'<verify>\s*([\s\S]*?)\s*</verify>', full_content)
verify_results = None
if verify_match:
    try:
        cases = json.loads(verify_match.group(1))
        verify_results = _run_verify_cases(cases)
    except (json.JSONDecodeError, ValueError) as e:
        verify_results = {"error": f"验证用例解析失败: {e}"}

# 将 verify_results 传入下一轮的 system prompt
if verify_results:
    system_prompt += "\n\n--- 测试验证结果 ---\n"
    for v in verify_results:
        icon = "✅" if v.get("passed") else "❌"
        system_prompt += f"{icon} 测试 {v['case']}: {'通过' if v.get('passed') else '失败'}\n"
        for d in v.get("details", []):
            status = "✅" if d.get("match") else "❌"
            system_prompt += f"  {status} {d['id']}: 期望={d['expected']}, 实际={d['actual']}\n"
        if "error" in v:
            system_prompt += f"  ⚠️ 错误: {v['error']}\n"
```

---

## 四、实施计划

### 4.1 改动汇总

| 文件 | 改动内容 | 类型 |
|---|---|---|
| `app.py` | 新增 `TOOL_DEFINITIONS` 常量 | 新增 |
| `app.py` | 修改 `_build_autonomous_system_prompt()` — 支持 JSON 工具格式、反馈注入 | 修改 |
| `app.py` | 修改 `_parse_commands_payload()` — 增加 JSON 解析分支 | 修改 |
| `app.py` | 新增 `_compute_state_diff()` — 状态差异计算 | 新增 |
| `app.py` | 新增 `_run_verify_cases()` — 自动测试执行 | 新增 |
| `app.py` | 修改 `call_llm_stream()` — diff 反馈 + 验证集成 | 修改 |
| `AI_INSTRUCTIONS.md` | 更新文档，加入 JSON 工具格式说明 | 更新 |

### 4.2 不变部分

| 文件 | 原因 |
|---|---|
| `ai_commands.py` | 命令执行逻辑独立，无需改动 |
| `static/scripts/chat.js` | 前端 UI 不参与后端 agent 逻辑变更 |
| `static/scripts/app.js` | 画布渲染不涉及 agent 改造 |
| `templates/index.html` | HTML 结构不变 |

### 4.3 风险控制

- **向后兼容**：JSON 工具调用作为新增格式加入，旧文本格式完整保留，新老版本 AI 和行为均不受影响
- **可逆部署**：每个 Phase 独立可测试，可按需启用/禁用
- **状态安全**：验证框架使用 `deepcopy` + `try/finally` 保证即便验证过程异常也能恢复电路原始状态
- **Token 安全**：diff 反馈系统不会丢失信息——完整的电路状态仍然可以通过 `compact_state_json` 按需获取

---

## 五、预期收益

| 指标 | 当前 | 优化后 |
|---|---|---|
| 命令解析成功率 | ~85%（依赖格式精确度） | ~99%（JSON 结构保证） |
| 每轮 token 消耗（中型电路 50 元件） | ~8K（全量状态） | ~1.5K（diff + IO 摘要） |
| 验证反馈轮次 | AI 手动 SET+SAMPLE → 额外 2-3 轮 | 自动执行 → 0 额外轮 |
| 错误恢复能力 | 震荡检测后硬停止 | 反馈驱动 → 针对性修复 |
