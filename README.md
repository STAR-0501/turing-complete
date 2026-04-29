# 逻辑电路模拟系统 (Turing Complete)

一个基于浏览器的数字逻辑电路模拟器，支持 **手动搭建** 与 **AI 自动搭建**，具备函数封装、嵌套函数、自动仿真等能力。

---

## 一、运行环境

**后端**
- Python 3.6+
- Flask 3.0+
- requests

**前端**
- 现代浏览器（Chrome / Edge / Firefox）

**AI（可选）**
- 兼容 OpenAI API 格式的大模型服务（如 DeepSeek、OpenAI、通义千问等）
- 默认使用 [DeepSeek API](https://platform.deepseek.com/)

---

## 二、快速开始

```bash
# 1. 安装依赖
pip install flask requests

# 2. （可选）配置 AI
#    编辑 app.py，将 AI_CONFIG["api_key"] 改为你的 API Key

# 3. 启动
python app.py

# 4. 打开浏览器访问
http://localhost:5000
```

---

## 三、项目架构

```
turing-complete/
├── app.py                  # Flask 后端：路由、AI 自治循环、会话管理
├── ai_commands.py           # 电路数据管理 + 布尔仿真引擎
├── circuit_data.json        # 电路持久化文件 (.gitignore)
├── functions_data.json      # 自定义函数持久化文件 (.gitignore)
├── static/
│   ├── scripts/
│   │   ├── app.js           # 前端主逻辑：拖拽、连线、工具切换、快捷键
│   │   ├── circuit.js       # 前端电路计算引擎
│   │   ├── chat.js          # AI 聊天窗口（流式 SSE + 指令执行）
│   │   ├── elements.js      # 元件模板定义
│   │   ├── renderer.js      # Canvas 渲染器
│   │   └── utils.js         # 工具函数
│   └── style/css/styles.css # 全局样式（赛博朋克风格）
└── templates/index.html     # 单页应用入口
```

### 后端核心模块 (`ai_commands.py`)

| 组件 | 职责 |
|------|------|
| `CircuitManager` | 电路持久化（原子写入）、元件/导线 CRUD |
| `SimulationContext` | 仿真上下文（elements、wires、depth） |
| `_simulate_elements_until_stable` | 迭代仿真直到所有信号稳定 |
| `_calc_and/or/not/output_state` | 各类型元件的状态计算（策略模式） |
| `_calculate_function_element` | 递归计算嵌套函数（深度上限 10） |

### 后端 API 路由 (`app.py`)

| 路由 | 功能 |
|------|------|
| `/api/save-circuit` | 保存电路到文件 |
| `/api/load-circuit` | 从文件加载电路 |
| `/api/ai/execute` | 执行单条电路指令 |
| `/api/ai/generate-comments` | AI 自动为元件生成中文注释 |
| `/api/ai/generate-layout` | AI 自动整理电路布局 |
| `/api/ai/generate-circuit` | 根据自然语言需求生成完整电路 |
| `/api/chat` | **AI 自治执行入口**（流式 SSE） |
| `/api/save-function` | 保存单个自定义函数 |
| `/api/save-functions` | 批量保存函数列表 |
| `/api/load-functions` | 加载函数列表 |

---

## 四、AI 自治执行模式

> 这是本项目的核心能力：AI 像写代码的 Agent 一样，**多轮计划→执行→检查→迭代** 直到完成。

### 工作流

1. **快速分类**：先判断用户意图是 `circuit`（需要电路操作）还是 `chat`（日常对话）
2. **chat 模式**：直接单次 LLM 调用回复，不进自治循环
3. **circuit 模式**：进入多轮循环：
   - 每轮读取当前电路状态，构建 system prompt
   - LLM 输出 `<plan> <answer> <commands> <verify> <done>` 结构
   - 流式接收时**逐条实时执行**指令，每执行一条刷新画布
   - 执行完后自动检查：状态变化、错误、验证用例
   - 如果未完成且未出错，继续下一轮

### AI 可用指令

| 指令 | 格式 | 说明 |
|------|------|------|
| ADD | `ADD <type> <x> <y> [alias]` | 添加元件（AND/OR/NOT/INPUT/OUTPUT/自定义函数） |
| WIRE | `WIRE <from> <from_port> <to> <to_port>` | 连接导线（端口从 0 开始） |
| MOVE | `MOVE <id_or_alias> <x> <y>` | 移动元件 |
| DEL | `DEL <id_or_alias>` | 删除元件 |
| DELW | `DELW <wire_id>` | 删除导线 |
| CLEAR | `CLEAR` | 清空画布 |
| TOGGLE | `TOGGLE <id_or_alias>` | 切换 INPUT 电平 |
| SET | `SET <id_or_alias> <0\|1>` | 设置 INPUT 为指定电平 |
| SIM | `SIM` | 显式触发仿真 |
| SAMPLE | `SAMPLE [id_or_alias ...]` | 采样 OUTPUT 状态 |
| DEFINE_FUNC | `DEFINE_FUNC <name>` | 将当前电路封装为函数 |
| COMMENT | `COMMENT <id_or_alias> <text>` | 设置元件注释 |

### 系统提示词包含的规则

- **命令上限**：每轮 ≤ 30 条，超出自动截断并提示下轮继续
- **函数思维**：复杂逻辑先搭建 → DEFINE_FUNC → SET+SAMPLE 验证 → CLEAR → 复用
- **坐标规则**：输入 x=80、门 x=240、输出 x=560，y 间距 80，后端有重叠自动修正
- **plan ≤ 80 字**：只写做什么 + 坐标策略，不写原理推导
- **验证驱动**：每完成子目标用 SET+SAMPLE 或 `<verify>` 做测试

---

## 五、手动操作

### 快捷键

| 键 | 功能 |
|----|------|
| 1 | 选择工具 |
| 2 | 输入切换工具 |
| 3 | 添加与门 |
| 4 | 添加或门 |
| 5 | 添加非门 |
| 6 | 添加输入 |
| 7 | 添加输出 |
| 8 | 删除工具 |
| 9 | 清空电路 |
| 0 | 切换网格 |
| Ctrl+Z | 撤销 |
| Ctrl+Y | 重做 |
| Ctrl+C | 复制选中元件 |
| Ctrl+V | 粘贴元件 |
| Ctrl+A | 全选 |
| Ctrl+S | 保存为函数 |
| Ctrl+D | 删除选中元件 |
| Esc | 取消操作 |

### 状态颜色

- **绿色**：信号 1
- **红色**：信号 0
- **灰色**：未连接

---

## 六、函数系统

1. 搭建包含 INPUT 和 OUTPUT 的完整子电路
2. 框选所有元件，按 `Ctrl+S` 或使用命令 `DEFINE_FUNC <name>`
3. 右侧面板出现函数名称，点击即可放置
4. 支持多层嵌套：函数内部可调用其他函数

---

## 七、高级功能

### 思考模式（DeepSeek 深度推理）

聊天输入框左侧有 **深度思考** 按钮，开启后：
- 后端发送 `reasoning_effort="high"` + `extra_body={"thinking": {"type": "enabled"}}`
- AI 会先输出思维链再给出最终答案（适合复杂电路设计）

### 自动注释

点击工具栏的 AI 注释按钮，AI 会自动为每个元件生成中文功能说明。

### 自动布局

点击工具栏的 AI 排版按钮，AI 会重新计算所有元件的位置使其布局清晰。

---

## 八、故障排除

| 问题 | 解决方案 |
|------|---------|
| 启动失败 | 检查 Python 版本和依赖安装 |
| 端口占用 | `app.py` 最后一行改 `port=5001` |
| AI 不工作 | 检查 `AI_CONFIG["api_key"]` 和网络连接 |
| 电路不计算 | 检查输入端是否都已连线 |
| 文件损坏 | 删除 `circuit_data.json` 和 `functions_data.json` 重启 |
