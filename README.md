# 逻辑电路模拟系统 (Turing Complete)

一个基于浏览器的数字逻辑电路模拟器，支持 **手动搭建** 与 **AI 自动搭建**，具备模块封装、嵌套模块、自动仿真等能力。

---

## 一、运行环境

**后端**
- Python 3.9+
- Flask 3.1+
- requests, pyyaml

**前端**
- 现代浏览器（Chrome / Edge / Firefox）

**AI（可选）**
- 兼容 OpenAI API 格式的大模型服务（如 DeepSeek、OpenAI、通义千问等）
- 默认使用 [DeepSeek API](https://platform.deepseek.com/)

---

## 二、快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （可选）配置 AI
#    编辑 ai_config.json，设置 api_key 和 model

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
├── agent_config.py          # AgentConfig 数据类，YAML 配置加载
├── instructions.py          # Instruction 分组管理，%%SCENARIO:xxx%% 标记
├── permissions.py           # 权限枚举 + TOOL_PERMISSIONS + PermissionChecker
├── retry.py                 # 指数退避重试机制
├── subagent_manager.py      # 子代理管理器（信号量并发控制）
├── turing_compactor.py      # 上下文溢出检测 + 智能压实
├── turing_skills.py         # 技能系统：SkillManager + skills/ 目录管理
├── templates/
│   └── index.html          # 单页应用入口
├── static/
│   ├── scripts/            # (见 static/scripts/AGENTS.md)
│   │   ├── app.js          # 前端主逻辑：拖拽、连线、工具切换、快捷键
│   │   ├── circuit.js      # 前端电路计算引擎
│   │   ├── renderer.js     # Canvas 渲染器
│   │   ├── chat.js         # AI 聊天窗口（流式 SSE + 指令执行）
│   │   ├── elements.js     # 元件模板定义
│   │   └── utils.js        # 工具模块
│   └── style/css/
│       └── styles.css      # 全局样式（赛博朋克风格）
├── skills/                 # 结构化技能定义（.md 文件）
├── turing_to_arduino/      # (见 turing_to_arduino/AGENTS.md) — Arduino 代码转换
├── docs/
│   └── superpowers/        # 设计文档（specs + 实施计划）
│       └── plans/          # 各机制的实施方案
├── agent_config.yaml       # YAML Agent 配置（启动时加载）
├── ai_config.json          # AI 提供商配置（API Key、模型等）
├── circuit_data.json       # 电路持久化文件 (.gitignore)
├── modules_data.json       # 自定义模块持久化文件 (.gitignore)
├── skills.md               # 自动生成的技能索引（注入 AI 提示词）
├── plan.md                 # AI 计划持久化
├── summary.md              # AI 会话摘要持久化
├── requirements.txt        # 依赖清单（flask, requests, pyyaml）
├── app.spec                # PyInstaller 打包配置
├── AI_INSTRUCTIONS.md      # AI 代理指令协议（文本 + JSON 双格式）
├── CLAUDE.md               # 编码 LLM 行为指南
├── README.md               # 项目说明
├── ROADMAP.md              # 项目路线图
└── log/                    # AI 对话日志 (JSONL, gitignored)
```

### 后端核心模块

| 文件 | 组件 | 职责 |
|------|------|------|
| `ai_commands.py` | `CircuitManager`, `SimulationContext` | 电路持久化、仿真引擎、指令执行 |
| `agent_config.py` | `AgentConfig` | Agent 配置数据类，YAML 文件加载 |
| `instructions.py` | `InstructionGroup`, `InstructionManager` | 指令分组管理，情景标记过滤 |
| `permissions.py` | `Permission`, `TOOL_PERMISSIONS`, `PermissionChecker` | 工具级权限检查（READ/EXEC/WRITE/ADMIN） |
| `retry.py` | `exponential_backoff`, `retry_call` | LLM 调用指数退避重试（3 次，最长 32s 间隔） |
| `subagent_manager.py` | `SubagentManager` | 子代理并发执行（信号量限流，120s 超时） |
| `turing_compactor.py` | `OverflowDetector`, `ContextCompactor` | Token 估算触发、历史对话智能压实 |
| `turing_skills.py` | `Skill`, `SkillManager` | 结构化技能加载、skills/ 目录发现 |

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
| `/api/save-function` | 保存单个自定义模块 |
| `/api/save-functions` | 批量保存模块列表 |
| `/api/load-functions` | 加载模块列表 |
| `/api/subagent` (POST) | 创建并派生子代理任务 |
| `/api/subagent/<id>` (GET) | 查询子代理任务状态与结果 |

---

## 四、AI 自治执行模式

> 这是本项目的核心能力：AI 像写代码的 Agent 一样，**多轮计划→执行→检查→迭代** 直到完成。

### 工作流

1. **快速分类**：先判断用户意图是 `circuit`（需要电路操作）还是 `chat`（日常对话）
2. **chat 模式**：直接单次 LLM 调用回复，不进自治循环
3. **circuit 模式**：进入多轮循环：
   - 每轮读取当前电路状态，构建 system prompt（含指令情景过滤、技能注入）
   - LLM 输出 `<plan> <answer> <commands> <verify> <done>` 结构
   - 流式接收时**逐条实时执行**指令，每执行一条刷新画布
   - 指令执行前经过**权限检查**（PermissionChecker）
   - LLM 调用带有**指数退避重试**（3 次，429/5xx 自动恢复）
   - 每轮结束后：**上下文压实**（OverflowDetector 估算 token，ContextCompactor 压缩历史，保留最近 2 轮）
   - 执行完后自动检查：状态变化、错误、验证用例
   - 如果未完成且未出错，继续下一轮

### AI 可用指令

| 指令 | 格式 | 说明 |
|------|------|------|
| ADD | `ADD <type> <x> <y> [alias]` | 添加元件（AND/OR/NOT/INPUT/OUTPUT/自定义模块） |
| WIRE | `WIRE <from> <from_port> <to> <to_port>` | 连接导线（端口从 0 开始） |
| MOVE | `MOVE <id_or_alias> <x> <y>` | 移动元件 |
| DEL | `DEL <id_or_alias>` | 删除元件 |
| DELW | `DELW <wire_id>` | 删除导线 |
| CLEAR | `CLEAR` | 清空画布 |
| TOGGLE | `TOGGLE <id_or_alias>` | 切换 INPUT 电平 |
| SET | `SET <id_or_alias> <0\|1>` | 设置 INPUT 为指定电平 |
| SIM | `SIM` | 显式触发仿真 |
| SAMPLE | `SAMPLE [id_or_alias ...]` | 采样 OUTPUT 状态 |
| DEFINE_FUNC | `DEFINE_FUNC <name>` | 将当前电路封装为模块 |
| COMMENT | `COMMENT <id_or_alias> <text>` | 设置元件注释 |

### 系统提示词包含的规则

- **上下文压实**：每轮结束后自动压实历史对话，保留最近 2 轮完整内容
- **模块思维**：复杂逻辑先搭建 → DEFINE_FUNC → SET+SAMPLE 验证 → CLEAR → 复用
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
| Ctrl+S | 保存为模块 |
| Ctrl+D | 删除选中元件 |
| Esc | 取消操作 |

### 状态颜色

- **绿色**：信号 1
- **红色**：信号 0
- **灰色**：未连接

---

## 六、模块系统

1. 搭建包含 INPUT 和 OUTPUT 的完整子电路
2. 框选所有元件，按 `Ctrl+S` 或使用命令 `DEFINE_FUNC <name>`
3. 右侧面板出现模块名称，点击即可放置
4. 支持多层嵌套：模块内部可调用其他模块

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
| AI 不工作 | 检查 `ai_config.json` 中的 `api_key` 和网络连接 |
| 电路不计算 | 检查输入端是否都已连线 |
| 文件损坏 | 删除 `circuit_data.json` 和 `modules_data.json` 重启 |
